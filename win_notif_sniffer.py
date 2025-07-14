# win_notif_sniffer.py

from pywinauto import Desktop

_known_toasts = set()

def scan_windows_toasts(callback=None):
    """
    Scrute une fois les toasts Windows et appelle le callback pour chaque toast nouveau.

    Args:
        callback (callable): fonction à appeler avec le titre du toast détecté.
    """
    windows = Desktop(backend="uia").windows()
    for w in windows:
        try:
            if "ToastWndClass" in w.class_name():
                title = w.window_text()
                if title and title not in _known_toasts:
                    _known_toasts.add(title)
                    if callback:
                        callback(title)
        except Exception:
            continue
