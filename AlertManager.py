#!/usr/bin/env python3
import re
import io
import threading
from threading import Lock
from typing import Dict, List, Optional
import pygame
from providers.groq_client import GroqClient
from providers.tts_client import TTSClient
from config import Config


class AlertManager:
    """Gestionnaire des alertes et communications"""
    
    def __init__(self, logger, http_session):
        self.logger = logger
        self.http_session = http_session
        self.groq_client = GroqClient(logger)
        self.tts_client = TTSClient(http_session, Config, logger)
        self.lock = Lock()
        self.currently_playing = False
    
    def generate_alert_message(self, analysis: Dict) -> str:
        system_prompt = (
            "Tu es une assistante vocale. Génère un message court (max 50 mots) "
            "En français pour alerter sur l'état du système. Sois technique et naturelle comme cortana dans Halo infinity, mais pas trop. utilise bien les pontuations."
            #"Exemples: 'CPU critique: 95 pourcent', 'RAM en hausse: 88 pourcent', 'Pic CPU détecté'"
        )
        
        user_prompt = self._create_alert_prompt(analysis)
        
        for model in Config.GROQ_MODELS:
            message = self.groq_client.chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=Config.GROQ_TEMPERATURE,
                max_tokens=Config.GROQ_MAX_TOKENS
            )
            if message:
                return message
        
        return self._create_fallback_message(analysis)
    
    def _create_alert_prompt(self, analysis: Dict) -> str:
        prompt = []
        for resource in ['cpu', 'ram', 'disk', 'temp']:
            if resource in analysis['metrics']:
                status = analysis['anomalies'].get(resource, {}).get('threshold', 'normal')
                prompt.append(
                    f"{resource.upper()}: {analysis['metrics'][resource]:.1f}% "
                    f"({status}, {analysis['trends'].get(resource, 'stable')})"
                )
        
        prompt.append(f"Statut global: {analysis['status']}")
        return " | ".join(prompt)
    
    def _create_fallback_message(self, analysis: Dict) -> str:
        main_issue = ""
        for resource in ['cpu', 'ram', 'disk', 'temp']:
            if analysis['anomalies'].get(resource, {}).get('threshold') == 'critical':
                main_issue = f"{resource} critique"
                break
        if not main_issue:
            for resource in ['cpu', 'ram', 'disk', 'temp']:
                if analysis['anomalies'].get(resource, {}).get('threshold') == 'warning':
                    main_issue = f"{resource} élevé"
                    break
        if not main_issue and analysis['status'] == 'spike':
            main_issue = "Pic système détecté"
        
        return f"Alerte: {main_issue}" if main_issue else "Alerte système"
    
    def text_to_speech(self, text: str) -> Optional[bytes]:
        try:
            voices = self.tts_client.get_available_voices(text)
            for lang in Config.TTS_VOICE_PREFERENCE:
                voice = next((v for v in voices if lang in v['ShortName']), None)
                if voice:
                    audio = self.tts_client.synthesize(text, voice['ShortName'])
                    if audio:
                        return audio
            if voices:
                return self.tts_client.synthesize(text, voices[0]['ShortName'])
            raise Exception("Aucune voix disponible")
        except Exception as e:
            self.logger.error(f"Erreur TTS: {e}")
            return None
    
    def play_alert(self, audio_data):
        if self.currently_playing:
            self.logger.warning("Une alerte est déjà en cours de lecture")
            return
        self.currently_playing = True
        
        def _play():
            try:
                with self.lock:
                    with io.BytesIO(audio_data) as audio_stream:
                        pygame.mixer.music.load(audio_stream)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            pygame.time.delay(100)
            except Exception as e:
                self.logger.error(f"Erreur de lecture audio: {e}")
            finally:
                self.currently_playing = False
        
        threading.Thread(target=_play, daemon=True).start()
        
        
    def reformulate_notification(self, text: str):
        """
        Reformule un texte brut d'une notification système pour lecture vocale.
        """
        system_prompt = (
            "Tu es un assistant vocal. Reformule ce texte pour le rendre fluide "
            "et agréable à écouter. Langue : français. Maximum 50 mots."
        )

        for model in Config.GROQ_MODELS:
            response = self.groq_client.chat_completion(
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
        self.logger.warning("Aucune reformulation réussie, retour du texte brut")
        return text