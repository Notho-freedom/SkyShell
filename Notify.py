# main.py
import time
import logging
from datetime import datetime, timedelta
from collections import deque
import numpy as np
import psutil
import pygame

from config import Config
from groq_manager import AlertManager

logger = logging.getLogger("SkyNotifyPro")

class SystemMonitor:
    """Surveillance avancée des ressources système"""
    
    def __init__(self):
        self.history = {
            'cpu': deque(maxlen=30),
            'ram': deque(maxlen=30),
            'disk': deque(maxlen=10),
            'temp': deque(maxlen=10)
        }
        self.alert_history = deque(maxlen=20)
        self.last_alert_time = None
        self.last_stable_time = datetime.now()
    
    # ... (méthodes inchangées)

def setup_logging():
    """Configure le système de logging"""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler('skynotify.log'),
            logging.StreamHandler()
        ]
    )

def main():
    """Point d'entrée principal"""
    setup_logging()
    pygame.mixer.init()
    pygame.mixer.music.set_volume(Config.AUDIO_VOLUME)
    
    try:
        monitor = SystemMonitor()
        alert_manager = AlertManager()
        
        while True:
            try:
                metrics = monitor.update_metrics()
                analysis = monitor.analyze_resources()
                
                if monitor.should_alert(analysis):
                    alert_message = alert_manager.generate_alert_message(analysis)
                    audio_data = alert_manager.text_to_speech(alert_message)
                    if audio_data:
                        alert_manager.play_alert(audio_data)
                        monitor.record_alert(analysis, alert_message)
                
                time.sleep(Config.CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Erreur dans la boucle principale: {e}")
                time.sleep(Config.CHECK_INTERVAL * 2)
                
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.critical(f"Erreur fatale: {e}")
    finally:
        pygame.mixer.quit()
        logger.info("SkyNotify Pro arrêté")

if __name__ == "__main__":
    main()