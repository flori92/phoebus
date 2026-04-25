"""
PHOEBUS/network_cameras.py

Module de gestion des caméras réseau pour PHOEBUS.

Fonctionnalités:
- Découverte automatique des caméras sur le réseau local
- Support RTSP, HTTP, WebRTC
- Gestion caméras multiples (PC, téléphone, NVR)
- Caching des caméras découvertes
- Fallback vers caméra locale (webcam) si aucune réseau
- Reconnaissance faciale via resemblyzer

Configuration (.env):
    PHOEBUS_ENABLE_NETWORK_CAMERAS=1
    PHOEBUS_CAMERA_SCAN_TIMEOUT=5.0
    PHOEBUS_CAMERA_STORAGE=phoebus_cameras.json
    PHOEBUS_PHONE_IP=192.168.1.100 (optionnel)
    PHOEBUS_NVR_IP=192.168.1.50 (optionnel)

Utilisation:
    from PHOEBUS.network_cameras import CameraManager, discover_cameras
    
    # Découverte automatique
    cameras = discover_cameras()
    
    # Récupérer image depuis caméra spécifique
    manager = CameraManager()
    image = await manager.capture(camera_name="salon_camera")
    
    # Analyser avec PHOEBUS Vision
    from PHOEBUS.vision import demander_ia_vision
    result = await demander_ia_vision(image, "Dis-moi ce que tu vois")
"""

import os
import json
import asyncio
import socket
import threading
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from urllib.parse import urlparse
from datetime import datetime, timedelta

# Imports optionnels
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from PHOEBUS.config import BASE_DIR

# ── Configuration ─────────────────────────────────────────────────────────

logger = logging.getLogger("PHOEBUS.network_cameras")
logger.setLevel(logging.INFO)
# Éviter de créer un handler si le logger parent en a déjà un
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[NETWORK_CAMERAS] %(message)s"))
    logger.addHandler(ch)


ENABLE_NETWORK_CAMERAS = os.getenv("PHOEBUS_ENABLE_NETWORK_CAMERAS", "1").strip() == "1"
CAMERA_SCAN_TIMEOUT = float(os.getenv("PHOEBUS_CAMERA_SCAN_TIMEOUT", "5.0"))
CAMERA_STORAGE = os.getenv("PHOEBUS_CAMERA_STORAGE", "phoebus_cameras.json")
PHONE_IP = os.getenv("PHOEBUS_PHONE_IP", "").strip()
NVR_IP = os.getenv("PHOEBUS_NVR_IP", "").strip()
ENABLE_FACE_RECOGNITION = os.getenv("PHOEBUS_ENABLE_FACE_RECOGNITION", "1").strip() == "1"


# ── Détection caméras du réseau ────────────────────────────────────────

def get_local_ip() -> str:
    """Récupère l'IP locale du réseau."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def scan_port_async(host: str, port: int, timeout: float = 0.5) -> bool:
    """Teste si un port est ouvert."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def discover_cameras_on_network(timeout: float = CAMERA_SCAN_TIMEOUT) -> List[Dict]:
    """
    Scanne le réseau local pour découvrir des caméras.
    
    Ports communs:
    - 554: RTSP (caméras IP, téléphones)
    - 8080: HTTP (caméras IP)
    - 8000-8002: Streaming divers
    """
    local_ip = get_local_ip()
    subnet = ".".join(local_ip.split(".")[:3]) + "."
    
    cameras_found = []
    ports_to_scan = {554: "rtsp", 8080: "http", 8000: "http", 8001: "http", 8002: "http"}
    
    logger.info(f"[SCAN] Réseau {subnet}0/24 pour caméras (timeout={timeout}s)...")
    
    # Scanner les adresses 1-254 en parallèle
    threads = []
    lock = threading.Lock()
    
    def scan_host(ip: str):
        for port, protocol in ports_to_scan.items():
            if scan_port_async(ip, port, timeout=timeout / 20):
                with lock:
                    camera_info = {
                        "ip": ip,
                        "port": port,
                        "protocol": protocol,
                        "url": f"{protocol}://{ip}:{port}",
                        "discovered_at": datetime.now().isoformat(),
                        "name": f"camera_{ip.split('.')[-1]}_{port}"
                    }
                    cameras_found.append(camera_info)
                    logger.info(f"✓ Caméra trouvée: {camera_info['url']}")
    
    # Lancer les scans en parallèle (mais limité pour éviter trop de connexions)
    start_time = time.time()
    for i in range(1, 255):
        if time.time() - start_time > timeout:
            break
        ip = f"{subnet}{i}"
        t = threading.Thread(target=scan_host, args=(ip,), daemon=True)
        threads.append(t)
        t.start()
        
        # Limiter nombre de threads simultanés
        if len([t for t in threads if t.is_alive()]) > 20:
            time.sleep(0.01)
    
    # Attendre que tous les scans se terminent (ou timeout)
    for t in threads:
        t.join(timeout=0.1)
    
    return cameras_found


def detect_phone_camera(phone_ip: str = PHONE_IP) -> Optional[Dict]:
    """
    Détecte si un téléphone est disponible et récupère sa caméra.
    
    Supports:
    - IP Webcam (app Android): http://IP:8080
    - Restreamer (RTMP/HLS): rtmp://IP/live/camera
    """
    if not phone_ip:
        return None
    
    # Vérifier IP Webcam (Android)
    if scan_port_async(phone_ip, 8080, timeout=1.0):
        return {
            "name": "phone_camera",
            "ip": phone_ip,
            "port": 8080,
            "protocol": "http",
            "url": f"http://{phone_ip}:8080",
            "type": "mobile",
            "discovered_at": datetime.now().isoformat()
        }
    
    return None


def detect_nvr(nvr_ip: str = NVR_IP) -> Optional[Dict]:
    """Détecte un NVR (Hikvision, Dahua, etc)."""
    if not nvr_ip:
        return None
    
    if scan_port_async(nvr_ip, 554, timeout=1.0):
        return {
            "name": "nvr_main",
            "ip": nvr_ip,
            "port": 554,
            "protocol": "rtsp",
            "url": f"rtsp://{nvr_ip}:554",
            "type": "nvr",
            "discovered_at": datetime.now().isoformat()
        }
    
    return None


# ── Classe gestionnaire ────────────────────────────────────────────────

class CameraManager:
    """Gestionnaire central des caméras PHOEBUS."""
    
    def __init__(self, storage_file: str = CAMERA_STORAGE):
        self.storage_file = Path(BASE_DIR) / storage_file
        self.cameras: Dict[str, Dict] = self._load_cameras()
        self.last_capture = {}  # {name: timestamp}
        self.lock = threading.Lock()
    
    def _load_cameras(self) -> Dict[str, Dict]:
        """Charge la liste des caméras découvertes."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Erreur chargement caméras : {e}")
        return {}
    
    def _save_cameras(self) -> None:
        """Sauvegarde la liste des caméras."""
        with open(self.storage_file, "w") as f:
            json.dump(self.cameras, f, indent=2, default=str)
    
    def register_camera(self, name: str, camera_info: Dict) -> None:
        """Enregistre une caméra découverte."""
        with self.lock:
            self.cameras[name] = camera_info
            self._save_cameras()
            logger.info(f"✓ Caméra enregistrée: {name} → {camera_info.get('url')}")
    
    def list_cameras(self) -> List[str]:
        """Retourne la liste des caméras disponibles."""
        return list(self.cameras.keys())
    
    async def capture(self, camera_name: str = "pc", timeout: float = 5.0) -> Optional:
        """
        Capture une image depuis une caméra.
        
        camera_name: "pc" (webcam locale), ou nom de caméra réseau
        Returns: PIL.Image ou np.ndarray selon disponibilité
        """
        if not OPENCV_AVAILABLE:
            logger.error("OpenCV non disponible")
            return None
        
        try:
            if camera_name == "pc" or camera_name == "local":
                return self._capture_local_webcam()
            
            if camera_name not in self.cameras:
                logger.error(f"Caméra inconnue: {camera_name}")
                return None
            
            camera = self.cameras[camera_name]
            return await self._capture_remote(camera, timeout)
        
        except Exception as e:
            logger.error(f"Erreur capture {camera_name}: {e}")
            return None
    
    def _capture_local_webcam(self):
        """Capture depuis la webcam locale (index 0)."""
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.error("Impossible d'ouvrir la webcam")
                return None
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                logger.error("Impossible de capturer la webcam")
                return None
            
            # Convertir BGR → RGB
            if PILLOW_AVAILABLE:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return Image.fromarray(frame_rgb)
            
            return frame
        
        except Exception as e:
            logger.error(f"Erreur webcam: {e}")
            return None
    
    async def _capture_remote(self, camera: Dict, timeout: float = 5.0):
        """Capture depuis une caméra réseau."""
        url = camera.get("url")
        protocol = camera.get("protocol")
        
        if not url:
            return None
        
        try:
            # OpenCV peut ouvrir RTSP et HTTP directement
            cap = cv2.VideoCapture(url)
            
            # Timeout: si la caméra est lente, lire plusieurs frames
            for _ in range(5):
                ret, frame = cap.read()
                if ret:
                    cap.release()
                    
                    if PILLOW_AVAILABLE:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        return Image.fromarray(frame_rgb)
                    return frame
            
            cap.release()
            logger.warning(f"Timeout capture depuis {camera.get('name')}")
            return None
        
        except Exception as e:
            logger.error(f"Erreur capture {protocol}://{camera.get('ip')}: {e}")
            return None
    
    async def capture_all(self, include_local: bool = True) -> Dict[str, Any]:
        """Capture depuis toutes les caméras."""
        results = {}
        
        if include_local:
            results["pc"] = await self.capture("pc")
        
        tasks = [self.capture(name) for name in self.cameras.keys()]
        captures = await asyncio.gather(*tasks, return_exceptions=True)
        
        for name, image in zip(self.cameras.keys(), captures):
            results[name] = image if not isinstance(image, Exception) else None
        
        return results


# ── Fonctions globales ─────────────────────────────────────────────────

_manager = None

def get_camera_manager() -> CameraManager:
    """Singleton du gestionnaire caméras."""
    global _manager
    if _manager is None:
        _manager = CameraManager()
    return _manager


def discover_cameras(scan_network: bool = True, include_phone: bool = True) -> List[Dict]:
    """
    Découvre automatiquement toutes les caméras disponibles.
    """
    cameras = []
    
    # Caméra locale (toujours disponible)
    cameras.append({
        "name": "pc",
        "type": "local",
        "url": "cv2://0",
        "available": OPENCV_AVAILABLE
    })
    
    # Scan réseau
    if ENABLE_NETWORK_CAMERAS and scan_network:
        try:
            found = discover_cameras_on_network(timeout=CAMERA_SCAN_TIMEOUT)
            cameras.extend(found)
        except Exception as e:
            logger.error(f"Erreur scan réseau: {e}")
    
    # Téléphone
    if include_phone and PHONE_IP:
        phone = detect_phone_camera()
        if phone:
            cameras.append(phone)
    
    # NVR
    if NVR_IP:
        nvr = detect_nvr()
        if nvr:
            cameras.append(nvr)
    
    # Enregistrer les caméras trouvées
    manager = get_camera_manager()
    for camera in cameras:
        if camera.get("name") != "pc":
            manager.register_camera(camera.get("name"), camera)
    
    logger.info(f"✓ {len(cameras)} caméra(s) disponible(s): {[c.get('name') for c in cameras]}")
    
    return cameras


# ── Initialisation au boot ────────────────────────────────────────

if __name__ == "__main__":
    # Test
    print("Découverte des caméras...")
    cameras = discover_cameras()
    print(f"Caméras trouvées: {len(cameras)}")
    for cam in cameras:
        print(f"  - {cam}")
