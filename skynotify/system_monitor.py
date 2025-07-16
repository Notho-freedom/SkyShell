#!/usr/bin/env python3
"""
SkyNotify Pro - Système avancé de surveillance et d'alertes vocales pour SkyOS
"""
import hashlib
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Optional
import subprocess
import numpy as np
import psutil
from config import Config
import subprocess

class SystemMonitor:
    """Surveillance avancée des ressources système sous Windows"""
    
    def __init__(self, logger):
        self.history = {
            'cpu': deque(maxlen=30),
            'ram': deque(maxlen=30),
            'disk': deque(maxlen=10),
            'temp': deque(maxlen=10),
            'gpu': deque(maxlen=10),
            'battery': deque(maxlen=10)
        }
        self.logger = logger
        self.alert_history = deque(maxlen=20)
        self.last_alert_time: Optional[datetime] = None
        self.last_stable_time: datetime = datetime.now()
        
    def update_metrics(self) -> Dict[str, float]:
        metrics = {
            'cpu': psutil.cpu_percent(interval=1),
            'ram': psutil.virtual_memory().percent,
            'disk': psutil.disk_usage('C:\\').percent,
            'temp': self._get_cpu_temp(),
            'gpu': self._get_gpu_usage(),
            'battery': self._get_battery_level(),
            'timestamp': datetime.now()
        }
        
        for key, value in metrics.items():
            if key != 'timestamp':
                self.history[key].append((metrics['timestamp'], value))
                
        return metrics
    
    def _get_cpu_temp(self) -> float:
        """
        Sur Windows, psutil ne retourne presque jamais la température CPU.
        On renvoie 0.0 par défaut si aucune lecture possible.
        """
        return 0.0

    def _get_gpu_usage(self) -> float:
        """
        Essaie de lire l'utilisation GPU via nvidia-smi sur Windows.
        Si NVIDIA absent ou erreur → 0.0
        """
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                usage = float(result.stdout.strip())
                return usage
            else:
                return 0.0
        except Exception as e:
            self.logger.debug(f"Impossible de lire l'usage GPU: {e}")
            return 0.0
    
    def _get_battery_level(self) -> float:
        """
        Retourne le pourcentage batterie sous Windows.
        """
        try:
            batt = psutil.sensors_battery()
            if batt:
                return batt.percent
            else:
                return 0.0
        except Exception as e:
            self.logger.debug(f"Impossible de lire la batterie: {e}")
            return 0.0
    
    def analyze_resources(self) -> Dict:
        analysis = {
            'status': 'normal',
            'metrics': {},
            'trends': {},
            'anomalies': {}
        }
        
        for resource in ['cpu', 'ram', 'disk', 'temp', 'gpu', 'battery']:
            if not self.history[resource]:
                continue
                
            values = [val for (_, val) in self.history[resource]]
            current = values[-1]
            
            analysis['metrics'][resource] = current
            analysis['trends'][resource] = self._calculate_trend(values)
            analysis['anomalies'][resource] = self._detect_anomalies(resource, values, current)
        
        analysis['status'] = self._determine_global_status(analysis)
        return analysis
    
    def _calculate_trend(self, values: List[float]) -> str:
        if len(values) < 3:
            return 'stable'
            
        x = np.arange(len(values))
        y = np.array(values)
        try:
            coeff = np.polyfit(x, y, 1)[0]
        except np.linalg.LinAlgError:
            return 'stable'
        
        if coeff > 0.5:
            return 'increasing'
        elif coeff < -0.5:
            return 'decreasing'
        return 'stable'
    
    def _detect_anomalies(self, resource: str, values: List[float], current: float) -> Dict:
        anomalies = {
            'spike': False,
            'threshold': None
        }
        
        if len(values) >= 4:
            avg_prev = np.mean(values[-4:-1])
            spike_threshold = Config.THRESHOLDS.get(resource, {}).get('spike', 0)
            if abs(current - avg_prev) > spike_threshold:
                anomalies['spike'] = True
        
        thresholds = Config.THRESHOLDS.get(resource, {})
        if current > thresholds.get('critical', 100):
            anomalies['threshold'] = 'critical'
        elif current > thresholds.get('warning', 100):
            anomalies['threshold'] = 'warning'
            
        return anomalies
    
    def _determine_global_status(self, analysis: Dict) -> str:
        for resource in ['cpu', 'ram', 'disk', 'temp', 'gpu', 'battery']:
            if analysis['anomalies'].get(resource, {}).get('threshold') == 'critical':
                return 'critical'
        for resource in ['cpu', 'ram', 'disk', 'temp', 'gpu', 'battery']:
            if analysis['anomalies'].get(resource, {}).get('threshold') == 'warning':
                return 'warning'
        for resource in ['cpu', 'ram', 'gpu']:
            if analysis['anomalies'].get(resource, {}).get('spike', False):
                return 'spike'
        return 'normal'
    
    def should_alert(self, analysis: Dict) -> bool:
        now = datetime.now()
        
        if analysis['status'] == 'normal':
            self.last_stable_time = now
            return False
        
        if self.last_alert_time and (now - self.last_alert_time) < timedelta(seconds=Config.MIN_ALERT_INTERVAL):
            return False
        
        if (now - self.last_stable_time) < timedelta(seconds=Config.STABILITY_PERIOD):
            return False
        
        alert_hash = self._generate_alert_hash(analysis)
        for past_alert in self.alert_history:
            if past_alert['hash'] == alert_hash:
                return False
                
        return True
    
    def record_alert(self, analysis: Dict, message: str):
        alert = {
            'timestamp': datetime.now(),
            'analysis': analysis,
            'message': message,
            'hash': self._generate_alert_hash(analysis)
        }
        self.alert_history.append(alert)
        self.last_alert_time = alert['timestamp']
    
    def _generate_alert_hash(self, analysis: Dict) -> str:
        hash_str = "".join(
            f"{res[:3]}:{analysis['metrics'].get(res, 0):.1f}|"
            for res in ['cpu', 'ram', 'disk', 'temp', 'gpu', 'battery']
        )
        return hashlib.sha256(hash_str.encode()).hexdigest()
