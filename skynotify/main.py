#!/usr/bin/env python3
"""
SkyNotify Pro - Système avancé de surveillance et d'alertes vocales pour SkyOS
"""
import time
import logging
import pygame
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from config import Config
from system_monitor import SystemMonitor
from alert_manager import AlertManager
from win_notif_sniffer import scan_windows_toasts


# ------------------------
# INITIALISATION
# ------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler('skynotify.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SkyNotify")

pygame.mixer.init()
pygame.mixer.music.set_volume(Config.AUDIO_VOLUME)

http_session = requests.Session()
retry_strategy = Retry(
    total=5,
    backoff_factor=0.5,
    status_forcelist=[500, 502, 503, 504]
)
http_session.mount("https://", HTTPAdapter(max_retries=retry_strategy))



monitor = SystemMonitor(logger)
alert_manager = AlertManager(logger, http_session)
# ------------------------
# MAIN
# ------------------------

def on_new_toast(title):
    logger.info(f"Notification interceptée: {title}")
    
    try:
        # Génère une reformulation courte via AlertManager (Groq)
        audio = alert_manager.reformulate_notification(title)

        if audio:
            alert_manager.play_alert(audio_data=audio)
        else:
            logger.warning("TTS indisponible pour la notification.")
    
    except Exception as e:
        logger.error(f"Erreur traitement toast: {e}")


def main():
    logger.info("Démarrage de SkyNotify Pro")
    
    try:
        while True:
            scan_windows_toasts(callback=on_new_toast)
            monitor.update_metrics()
            analysis = monitor.analyze_resources()
            
            logger.debug(f"Analyse système: {analysis}")
            
            if monitor.should_alert(analysis):
                logger.warning(f"Déclenchement alerte: {analysis['status']}")
                
                alert_message = alert_manager.generate_alert_message(analysis)
                logger.info(f"Message alerte: {alert_message}")
                
                audio_data = alert_manager.text_to_speech(alert_message)
                if audio_data:
                    alert_manager.play_alert(audio_data)
                    monitor.record_alert(analysis, alert_message)
                else:
                    logger.error("Échec génération audio")
            
            time.sleep(Config.CHECK_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.critical(f"Erreur fatale: {e}")
    finally:
        pygame.mixer.quit()
        logger.info("SkyNotify Pro arrêté")

if __name__ == "__main__":
    main()
