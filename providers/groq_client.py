# providers/groq_client.py

import groq
from config import Config
import re
from config import Config

class GroqClient:
    """
    Wrapper réutilisable autour du client Groq.
    """

    def __init__(self, logger):
        self.logger = logger
        self.client = self._init_client()
        Config.GROQ_MODELS = self.list_models()

    def _init_client(self):
        try:
            client = groq.Client(api_key=Config.GROQ_API_KEY)
            return client
        except Exception as e:
            self.logger.error(f"Erreur d'initialisation Groq : {e}")
            raise

    def list_models(self):
        """
        Retourne la liste des modèles disponibles.
        """
        try:
            response = self.client.models.list()
            return [model.id for model in response.data]
        except Exception as e:
            self.logger.error(f"Impossible de récupérer la liste des modèles Groq : {e}")
            return []

    def chat_completion(self, model: str, messages: list, temperature: float, max_tokens: int):
        """
        Effectue un appel completions avec Groq.
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return self._sanitize_message(str(response.choices[0].message.content))
        except Exception as e:
            self.logger.warning(f"Erreur Groq completion (modèle {model}) : {e}")
            Config.GROQ_MODELS.remove(model)
            return None

    def _sanitize_message(self, text: str) -> str:
        text = re.sub(r"<[^>]*>", "", text)
        text = re.sub(r"[^\w\sÀ-ÿ.,!?'-]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text