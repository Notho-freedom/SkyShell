import json
import time
import uuid
from datetime import datetime

import psutil
import win32gui
import win32process
import win32con
from neo4j import GraphDatabase


class Neo4jClient:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def run_query(self, query, parameters=None):
        with self.driver.session() as session:
            session.run(query, parameters or {})


class SkyShellMonitor:
    def __init__(self, neo4j_client, interval_sec=5, json_output_path="skyshell_processes.json"):
        self.neo4j = neo4j_client
        self.interval_sec = interval_sec
        self.json_output_path = json_output_path

        self.last_obs_id = None
        self.last_active_app = None

    def run(self):
        """Boucle principale du watcher"""
        while True:
            active_app_data = self.list_processes_with_windows(
                prev_obs_id=self.last_obs_id,
                prev_active_app=self.last_active_app
            )

            if active_app_data:
                active_app_name = active_app_data["name"]
                obs_id = active_app_data["obs_id"]

                if active_app_name != self.last_active_app:
                    print(f"✨ SkyShell detected new active app: {active_app_name}")

                self.last_obs_id = obs_id
                self.last_active_app = active_app_name

            time.sleep(self.interval_sec)

    def list_processes_with_windows(self, prev_obs_id=None, prev_active_app=None):
        window_list = self.get_open_windows()
        windows_by_pid = {}
        for win in window_list:
            pid = win["pid"]
            windows_by_pid.setdefault(pid, []).append(win)

        active_window = self.get_foreground_window()
        active_pid = active_window["pid"] if active_window else None

        processes_info = []
        active_proc_data = None

        for proc in psutil.process_iter(attrs=['pid', 'name', 'exe']):
            try:
                pid = proc.info['pid']
                name = proc.info['name']
                exe = proc.info['exe'] or ""

                if self.is_system_process(exe):
                    continue

                process_data = {
                    "pid": pid,
                    "name": name,
                    "exe": exe,
                    "windows": [],
                    "is_visible": False,
                    "is_minimized": False
                }

                if pid in windows_by_pid:
                    for win in windows_by_pid[pid]:
                        process_data["windows"].append({
                            "title": win["title"],
                            "is_visible": win["is_visible"],
                            "is_minimized": win["is_minimized"]
                        })

                    process_data["is_visible"] = any(
                        w["is_visible"] and not w["is_minimized"] for w in process_data["windows"]
                    )
                    process_data["is_minimized"] = any(w["is_minimized"] for w in process_data["windows"])

                if pid == active_pid:
                    active_proc_data = process_data

                processes_info.append(process_data)

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Optionnel : sauvegarde JSON
        self.save_json(processes_info)

        if active_proc_data and active_window:
            timestamp = datetime.now()
            obs_id, active_app_name = self.push_to_neo4j(
                processes_info,
                active_pid,
                timestamp,
                prev_obs_id=prev_obs_id,
                prev_active_app=prev_active_app
            )
            return {
                "name": active_proc_data["name"],
                "obs_id": obs_id
            }

        return None

    def push_to_neo4j(self, processes_info, active_pid, timestamp, prev_obs_id=None, prev_active_app=None):
        observation_id = str(uuid.uuid4())
        day_str = timestamp.strftime("%Y-%m-%d")
        hour_str = timestamp.strftime("%H")

        # Day / Time
        self.neo4j.run_query("""
            MERGE (d:Day {date: $day})
            MERGE (t:Time {hour: $hour})
            MERGE (t)-[:IN_DAY]->(d)
        """, dict(day=day_str, hour=hour_str))

        # Observation node
        self.neo4j.run_query("""
            CREATE (obs:Observation {
                uuid: $uuid,
                timestamp: $timestamp
            })
            MERGE (t:Time {hour: $hour})
            MERGE (obs)-[:AT_TIME]->(t)
        """, dict(uuid=observation_id, timestamp=timestamp.isoformat(), hour=hour_str))

        app_names = []
        active_app_name = None

        for proc in processes_info:
            app_names.append(proc["name"])

            # Create App node
            self.neo4j.run_query("""
                MERGE (a:App {name: $name, exe: $exe})
                ON CREATE SET a.created_at = $now
                SET a.last_seen = $now
                MERGE (obs:Observation {uuid: $obs_uuid})
                MERGE (obs)-[:OBSERVED]->(a)
            """, dict(name=proc["name"], exe=proc["exe"],
                      now=timestamp.isoformat(), obs_uuid=observation_id))

            # Create Windows nodes
            for win in proc["windows"]:
                self.neo4j.run_query("""
                    MERGE (w:Window {title: $title})
                    MERGE (a:App {name: $name, exe: $exe})
                    MERGE (a)-[:HAS_WINDOW]->(w)
                """, dict(title=win["title"], name=proc["name"], exe=proc["exe"]))

            # Mark active app
            if proc["pid"] == active_pid:
                active_app_name = proc["name"]
                self.neo4j.run_query("""
                    MATCH (a:App {name: $name, exe: $exe})
                    MATCH (obs:Observation {uuid: $obs_uuid})
                    MERGE (a)-[r:WAS_ACTIVE_IN]->(obs)
                    ON CREATE SET r.count = 1
                    ON MATCH SET r.count = r.count + 1
                """, dict(name=proc["name"], exe=proc["exe"],
                          obs_uuid=observation_id))

        # Create USED_WITH relations
        for i in range(len(app_names)):
            for j in range(i + 1, len(app_names)):
                if app_names[i] != app_names[j]:
                    self.neo4j.run_query("""
                        MATCH (a1:App {name: $name1})
                        MATCH (a2:App {name: $name2})
                        MERGE (a1)-[r:USED_WITH]->(a2)
                        ON CREATE SET r.count = 1
                        ON MATCH SET r.count = r.count + 1
                    """, dict(name1=app_names[i], name2=app_names[j]))

        # NEXT_OBSERVATION relation
        if prev_obs_id:
            self.neo4j.run_query("""
                MATCH (prev:Observation {uuid: $prev_obs})
                MATCH (curr:Observation {uuid: $curr_obs})
                MERGE (prev)-[:NEXT_OBSERVATION]->(curr)
            """, dict(prev_obs=prev_obs_id, curr_obs=observation_id))

        # SWITCHED_FROM relation
        if prev_active_app and active_app_name and prev_active_app != active_app_name:
            self.neo4j.run_query("""
                MATCH (a1:App {name: $prev_app})
                MATCH (a2:App {name: $curr_app})
                MERGE (a1)-[r:SWITCHED_FROM]->(a2)
                ON CREATE SET r.count = 1, r.last_at = $timestamp
                ON MATCH SET r.count = r.count + 1, r.last_at = $timestamp
            """, dict(prev_app=prev_active_app,
                      curr_app=active_app_name,
                      timestamp=timestamp.isoformat()))

        return observation_id, active_app_name

    def save_json(self, processes_info):
        with open(self.json_output_path, "w", encoding="utf-8") as f:
            json.dump(processes_info, f, indent=4, ensure_ascii=False)

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def is_system_process(exe_path):
        if not exe_path:
            return False
        exe_lower = exe_path.lower()
        return exe_lower.startswith(r"c:\windows\system32") or \
               exe_lower.startswith(r"c:\windows\syswow64")
