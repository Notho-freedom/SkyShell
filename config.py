# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration centralisée du système"""
    
    # Groq
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODELS = ["mixtral-8x7b-32768", "llama3-70b-8192"]
    GROQ_TEMPERATURE = 0.3
    GROQ_MAX_TOKENS = 100
    
    # Seuils de ressources
    THRESHOLDS = {
        'cpu': {
            'warning': 70.0,
            'critical': 85.0,
            'spike': 15.0
        },
        'ram': {
            'warning': 70.0,
            'critical': 85.0,
            'spike': 15.0
        },
        'disk': {
            'warning': 90.0,
            'critical': 95.0
        },
        'temp': {
            'warning': 60.0,
            'critical': 85.0
        },
        'gpu': {
            'warning': 70.0,
            'critical': 90.0,
            'spike': 20.0
        },
        'battery': {
            'warning': 30.0,
            'critical': 15.0
        }
    }
    
    # Intervalles
    CHECK_INTERVAL = 10
    MIN_ALERT_INTERVAL = 120
    STABILITY_PERIOD = 60
    
    # TTS
    TTS_ENDPOINTS = {
        'voices': "https://low-tts.onrender.com/api/voices-by-text",
        'generate': "https://low-tts.onrender.com/api/tts"
    }
    TTS_TIMEOUT = 30
    TTS_VOICE_PREFERENCE = ['fr-FR', 'en-US']
    
    # Audio
    AUDIO_VOLUME = 0.8
