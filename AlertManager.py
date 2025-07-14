#!/usr/bin/env python3
import io
import threading
from threading import Lock
from typing import Dict, Optional
import pygame
from providers.groq_client import GroqClient
from providers.tts_client import TTSClient
from config import Config


class AlertManager:
    """
    Gestionnaire des alertes et communications pour SkyOS
    """

    def __init__(self, logger, http_session):
        self.logger = logger
        self.http_session = http_session
        self.groq_client = GroqClient(logger)
        self.tts_client = TTSClient(http_session, Config, logger)
        self.lock = Lock()
        self.currently_playing = False

    def generate_alert_message(self, analysis: Dict) -> str:
        """
        Génère un message d'alerte via l'IA Groq.
        """
        prompt = self._format_analysis_prompt(analysis)
        message = self._ask_groq(
            system_prompt=(
                "Tu es une assistante vocale. Génére un message court (max 50 mots) "
                "en français pour alerter sur l'état du système. Sois technique et naturelle comme Cortana "
                "dans Halo Infinity, mais pas trop. Utilise bien les ponctuations."
            ),
            user_prompt=prompt
        )
        return message or self._fallback_alert_message(analysis)

    def reformulate_notification(self, text: str) -> Optional[bytes]:
        """
        Reformule une notification système pour la rendre agréable à écouter.
        """
        message = self._ask_groq(
            system_prompt=(
                "Tu es un assistant vocal. Reformule ce texte pour le rendre fluide "
                "et agréable à écouter. Langue : français. Maximum 50 mots."
            ),
            user_prompt=text
        )
        if message:
            return self.text_to_speech(message)
        self.logger.warning("Aucune reformulation réussie, texte original conservé.")
        return None

    def _ask_groq(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """
        Interroge Groq pour obtenir une réponse textuelle.
        """
        for model in Config.GROQ_MODELS:
            response = self.groq_client.chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=Config.GROQ_TEMPERATURE,
                max_tokens=Config.GROQ_MAX_TOKENS
            )
            if response:
                return response
            self.logger.warning(f"Groq n'a pas répondu avec le modèle {model}")
        return None

    def _format_analysis_prompt(self, analysis: Dict) -> str:
        """
        Prépare un résumé structuré de l'analyse système à injecter dans le prompt IA.
        """
        segments = []
        for resource in ['cpu', 'ram', 'disk', 'temp']:
            if resource in analysis['metrics']:
                value = analysis['metrics'][resource]
                status = analysis['anomalies'].get(resource, {}).get('threshold', 'normal')
                trend = analysis['trends'].get(resource, 'stable')
                segments.append(f"{resource.upper()}: {value:.1f}% ({status}, {trend})")
        segments.append(f"Statut global: {analysis['status']}")
        return " | ".join(segments)

    def _fallback_alert_message(self, analysis: Dict) -> str:
        """
        Génère un message basique si l'IA Groq échoue.
        """
        for resource in ['cpu', 'ram', 'disk', 'temp']:
            if analysis['anomalies'].get(resource, {}).get('threshold') == 'critical':
                return f"Alerte : {resource} critique."
        for resource in ['cpu', 'ram', 'disk', 'temp']:
            if analysis['anomalies'].get(resource, {}).get('threshold') == 'warning':
                return f"Alerte : {resource} élevé."
        if analysis['status'] == 'spike':
            return "Alerte : pic système détecté."
        return "Alerte système."

    def text_to_speech(self, text: str) -> Optional[bytes]:
        """
        Convertit du texte en audio via le TTS.
        """
        try:
            voices = self.tts_client.get_available_voices(text)
            for lang in Config.TTS_VOICE_PREFERENCE:
                voice = next((v for v in voices if lang in v['ShortName']), None)
                if voice:
                    return self.tts_client.synthesize(text, voice['ShortName'])
            if voices:
                return self.tts_client.synthesize(text, voices[0]['ShortName'])
            raise RuntimeError("Aucune voix disponible pour la synthèse vocale.")
        except Exception as e:
            self.logger.error(f"Erreur TTS : {e}")
            return None

    def play_alert(self, audio_data: bytes):
        """
        Lecture audio d'une alerte via pygame, thread-safe.
        """
        if self.currently_playing:
            self.logger.warning("Une alerte est déjà en cours de lecture.")
            return

        def _play():
            try:
                with self.lock:
                    with io.BytesIO(audio_data) as stream:
                        pygame.mixer.music.load(stream)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            pygame.time.delay(100)
            except Exception as e:
                self.logger.error(f"Erreur lecture audio : {e}")
            finally:
                self.currently_playing = False

        self.currently_playing = True
        threading.Thread(target=_play, daemon=True).start()


