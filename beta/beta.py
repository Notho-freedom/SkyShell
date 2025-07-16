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
from SkyNotify.config import Config
from SkyNotify.SystemMonitor import SystemMonitor
from beta.beta_am import AlertManager
from SkyNotify.win_notif_sniffer import scan_windows_toasts


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
# HANDLER TOAST
# ------------------------

def on_new_toast(title):
    logger.info(f"Notification interceptée: {title}")

    try:
        audio = alert_manager.reformulate_notification(title)
        if audio:
            alert_manager.play_alert(audio_data=audio)
        else:
            logger.warning("TTS indisponible pour la notification.")
    except Exception as e:
        logger.error(f"Erreur traitement toast: {e}")

# ------------------------
# MAIN LOOP
# ------------------------

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

                # Nouvelle génération de payload JSON :
                alert_payload = alert_manager.generate_alert_payload(analysis)

                if alert_payload:
                    # Lecture vocale :
                    audio = alert_manager.text_to_speech(alert_payload.alert)
                    if audio:
                        alert_manager.play_alert(audio)
                    else:
                        logger.error("Échec de synthèse vocale.")

                    # Logging clair :
                    logger.info(
                        f"🚨 ALERTE : {alert_payload.alert} | "
                        f"Gravité : {alert_payload.severity}"
                    )

                    # Exécution action recommandée :
                    if alert_payload.action:
                        logger.info(f"⚙️ Exécution action recommandée : {alert_payload.action}")
                        alert_manager.execute_action(alert_payload.action)

                    # Historique :
                    monitor.record_alert(
                        analysis,
                        alert_payload.alert
                    )
                else:
                    logger.error("Impossible de générer une alerte structurée.")
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
