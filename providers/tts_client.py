# providers/tts_client.py

import io
from typing import Optional

class TTSClient:
    """
    Wrapper générique autour de ton backend TTS (Low-TTS, etc.)
    """

    def __init__(self, http_session, config, logger):
        self.http = http_session
        self.config = config
        self.logger = logger

    def get_available_voices(self, text: str):
        try:
            response = self.http.post(
                self.config.TTS_ENDPOINTS["voices"],
                json={"text": text},
                timeout=self.config.TTS_TIMEOUT
            )
            response.raise_for_status()
            return response.json().get("female_voices", [])
        except Exception as e:
            self.logger.error(f"Erreur récupération voix TTS : {e}")
            return []

    def synthesize(self, text: str, voice: str) -> Optional[bytes]:
        try:
            response = self.http.post(
                self.config.TTS_ENDPOINTS["generate"],
                json={"text": text, "voice": voice},
                timeout=self.config.TTS_TIMEOUT
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            self.logger.warning(f"Erreur synthèse vocale ({voice}) : {e}")
            return None
