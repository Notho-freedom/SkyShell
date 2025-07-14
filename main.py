import psutil
import win32gui
import win32process
import win32con
import json
import time
from neo4j import GraphDatabase
from datetime import datetime

NEO4J_URI = "neo4j+s://eac1883e.databases.neo4j.io"
NEO4J_USER = "neo4j"
NEO4J_PASS = "BfYuTIta_wx6hkyLleCVk7TqEb0NsH3OWbVmeIIk6uw"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

def push_to_neo4j(process_data, timestamp):
    """
    Push les données brutes d’un processus dans Neo4j :
    - nœud App avec nom, chemin exe, visible, minimisé
    - nœud Time (heure)
    - relation USED_AT avec compteur
    """
    with driver.session() as session:
        session.run("""
            MERGE (a:App {name: $name})
            ON CREATE SET a.exe_path = $exe_path,
                          a.usage_count = 1
            ON MATCH SET a.usage_count = a.usage_count + 1

            SET a.last_seen = $last_seen,
                a.visible = $visible,
                a.minimized = $minimized

            MERGE (t:Time {hour: $hour})
            MERGE (a)-[r:USED_AT]->(t)
            ON CREATE SET r.count = 1
            ON MATCH SET r.count = r.count + 1
        """, 
        name=process_data["name"],
        exe_path=process_data["exe"],
        visible=process_data["is_visible"],
        minimized=process_data["is_minimized"],
        last_seen=timestamp.isoformat(),
        hour=timestamp.strftime("%H")
        )

def get_open_windows():
    windows = []

    def enum_window_callback(hwnd, extra):
        title = win32gui.GetWindowText(hwnd).strip()
        if title:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            is_visible = bool(win32gui.IsWindowVisible(hwnd))
            is_minimized = bool(style & win32con.WS_MINIMIZE)
            windows.append({
                "hwnd": hwnd,
                "pid": pid,
                "title": title,
                "is_visible": is_visible,
                "is_minimized": is_minimized
            })

    win32gui.EnumWindows(enum_window_callback, None)
    return windows

def get_foreground_window():
    hwnd = win32gui.GetForegroundWindow()
    if hwnd:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        title = win32gui.GetWindowText(hwnd).strip()
        if title:
            return {
                "hwnd": hwnd,
                "pid": pid,
                "title": title
            }
    return None

def is_system_process(exe_path):
    if not exe_path:
        return False
    exe_lower = exe_path.lower()
    return exe_lower.startswith(r"c:\windows\system32") or \
           exe_lower.startswith(r"c:\windows\syswow64")

def list_processes_with_windows():
    window_list = get_open_windows()
    windows_by_pid = {}
    for win in window_list:
        pid = win["pid"]
        windows_by_pid.setdefault(pid, []).append(win)

    active_window = get_foreground_window()
    active_pid = active_window["pid"] if active_window else None
    active_title = active_window["title"] if active_window else None

    processes_info = []
    active_proc_data = None

    for proc in psutil.process_iter(attrs=['pid', 'name', 'exe']):
        try:
            pid = proc.info['pid']
            name = proc.info['name']
            exe = proc.info['exe'] or ""

            if is_system_process(exe):
                continue

            process_data = {
                "pid": pid,
                "name": name,
                "exe": exe,
                "windows": [],
                "category": "background",  # juste pour info brute, peut-être inutile
                "is_visible": False,
                "is_minimized": False
            }

            if pid in windows_by_pid:
                # Récupère premier état visible / minimisé pour ce process
                for win in windows_by_pid[pid]:
                    process_data["windows"].append({
                        "title": win["title"],
                        "is_visible": win["is_visible"],
                        "is_minimized": win["is_minimized"]
                    })
                # Données brutes visibles/minimisées: on peut garder un flag global, exemple:
                process_data["is_visible"] = any(w["is_visible"] and not w["is_minimized"] for w in process_data["windows"])
                process_data["is_minimized"] = any(w["is_minimized"] for w in process_data["windows"])

            if pid == active_pid:
                active_proc_data = process_data

            processes_info.append(process_data)

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # Save JSON (optionnel)
    with open("skyshell_processes.json", "w", encoding="utf-8") as f:
        json.dump(processes_info, f, indent=4, ensure_ascii=False)

    # Push vers Neo4j uniquement si on a une app active
    if active_proc_data and active_window:
        timestamp = datetime.now()
        push_to_neo4j(active_proc_data, timestamp)
        return active_proc_data["name"]

    return None

def watcher_loop(interval_sec=5):
    last_active_app = None

    while True:
        active_app = list_processes_with_windows()

        if active_app and active_app != last_active_app:
            print(f"✨ SkyShell detected new active app: {active_app}")
            last_active_app = active_app

        time.sleep(interval_sec)

if __name__ == "__main__":
    watcher_loop()
