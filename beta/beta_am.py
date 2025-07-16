# alert_manager.py
import io
import json
import re
import threading
from typing import Dict, Optional, List
from functools import cached_property

import pygame
from pydantic import BaseModel

from providers.groq_client import GroqClient
from providers.tts_client import TTSClient
from SkyNotify.config import Config


class AlertPayload(BaseModel):
    alert: str
    severity: str
    action: Optional[str]


class AlertManager:
    """Gestionnaire des alertes, reformulations et actions post-alertes"""

    def __init__(self, logger, http_session):
        self.logger = logger
        self.http_session = http_session
        self._lock = threading.Lock()
        self._playing = False

    @cached_property
    def groq(self) -> GroqClient:
        return GroqClient(self.logger)

    @cached_property
    def tts(self) -> TTSClient:
        return TTSClient(self.http_session, Config, self.logger)



    def generate_alert_payload(self, analysis: Dict) -> Optional[AlertPayload]:
        system_prompt = (
            "Tu es une IA système. Tu dois répondre STRICTEMENT par un JSON valide, sans aucun texte autour. "
            "Format attendu : {\"alert\":\"...\", \"severity\":\"...\", \"action\":\"...\"}. "
            "Langue : français uniquement."
        )

        prompt = self._format_prompt(analysis)

        for model in Config.GROQ_MODELS:
            message = self.groq.chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=Config.GROQ_TEMPERATURE,
                max_tokens=Config.GROQ_MAX_TOKENS
            )

            if message:
                json_str = None

                # 1. Essayer un parsing direct
                try:
                    return AlertPayload(**json.loads(message))
                except json.JSONDecodeError:
                    self.logger.warning("Réponse non JSON brut, tentative extraction via regex…")

                # 2. Extraction via regex d'un bloc JSON
                matches = re.findall(r'\{.*?\}', message, re.DOTALL)
                for m in matches:
                    try:
                        payload = json.loads(m)
                        return AlertPayload(**payload)
                    except json.JSONDecodeError:
                        continue

                # Si on est là, tout a échoué
                self.logger.error(f"Erreur de parsing JSON après toutes tentatives. Réponse brute : {message}")

        return None


    def _format_prompt(self, analysis: Dict) -> str:
        """
        Crée un prompt complet incluant toutes les métriques connues
        """
        lines = []
        for res in Config.THRESHOLDS.keys():
            if res in analysis['metrics']:
                metric = analysis['metrics'][res]
                anomaly = analysis['anomalies'].get(res, {})
                threshold = anomaly.get('threshold', 'ok')
                trend = analysis['trends'].get(res, 'stable')
                # Selon type de ressource, format différent (e.g. temp en °C)
                if res == "temp":
                    value_str = f"{metric:.1f}°C"
                elif res == "battery":
                    value_str = f"{metric:.1f}%"
                else:
                    value_str = f"{metric:.1f}%"

                lines.append(
                    f"{res.upper()}: {value_str} "
                    f"({threshold}, {trend})"
                )

        lines.append(f"Statut global: {analysis['status']}")
        return " | ".join(lines)

    def reformulate_notification(self, text: str) -> Optional[bytes]:
        system_prompt = (
            "Tu es un assistant vocal. Reformule ce texte système pour une lecture naturelle, max 50 mots."
        )
        for model in Config.GROQ_MODELS:
            response = self.groq.chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=Config.GROQ_TEMPERATURE,
                max_tokens=Config.GROQ_MAX_TOKENS
            )
            if response:
                return self.text_to_speech(response)
        return None

    def text_to_speech(self, text: str) -> Optional[bytes]:
        try:
            voices = self.tts.get_available_voices(text)
            for lang in Config.TTS_VOICE_PREFERENCE:
                voice = next((v for v in voices if lang in v['ShortName']), None)
                if voice:
                    return self.tts.synthesize(text, voice['ShortName'])
            if voices:
                return self.tts.synthesize(text, voices[0]['ShortName'])
        except Exception as e:
            self.logger.error(f"Erreur TTS: {e}")
        return None

    def play_alert(self, audio_data: bytes):
        if self._playing:
            self.logger.warning("Lecture déjà en cours.")
            return

        self._playing = True

        def _play():
            try:
                with self._lock, io.BytesIO(audio_data) as stream:
                    pygame.mixer.music.load(stream)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        pygame.time.delay(100)
            except Exception as e:
                self.logger.error(f"Erreur audio: {e}")
            finally:
                self._playing = False

        threading.Thread(target=_play, daemon=True).start()

    def execute_action(self, action: str):
        import subprocess
        try:
            result = subprocess.run(action, shell=True, capture_output=True, text=True)
            self.logger.info(f"[ACTION EXEC] → {action}\nRésultat:\n{result.stdout}")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution de l'action: {e}")
