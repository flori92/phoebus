"""Caméras de PHOEBUS : webcam PC, caméra IP, caméra téléphone (via WS).

Trois sources d'images en temps réel :

1. **PC** : la webcam interne du Mac/PC via OpenCV. Capture rapide locale
   (~150 ms), aucune dépendance réseau.

2. **Téléphone** (via mobile/app.js) : on demande au client mobile
   authentifié de capturer une frame de sa caméra arrière (ou frontale)
   et de la renvoyer via WebSocket en base64. Pattern similaire à
   `PENDING_SCREEN_CAPTURES`. Latence ~500 ms-1 s selon le réseau.

3. **Caméra IP** : URL d'un endpoint snapshot type `http://192.168.x.x/snapshot.jpg`
   ou flux MJPEG. Compatible RTSP via OpenCV. Utile pour caméras de
   surveillance, doorbell, frigo connecté, etc.

Toutes les sources renvoient des bytes JPEG. La fonction
`analyser_image()` les pousse au LLM vision (Gemini Vision par défaut,
ou Arena Claude pour les analyses fines) avec une question en langage
naturel et renvoie la réponse texte.

Configuration (.env) :
    PHOEBUS_CAMERA_PC_INDEX=0       # index OpenCV de la webcam (0=interne)
    PHOEBUS_CAMERA_PHONE_TIMEOUT=8  # délai max attente du mobile (secondes)
    PHOEBUS_CAMERA_IP_URL=http://192.168.1.20/snapshot  # caméra IP par défaut
"""
import asyncio
import base64
import io
import os
import time
import uuid
from typing import Optional

import requests

import PHOEBUS.state as state
from PHOEBUS.config import client, types, MODELS_LIST
from PHOEBUS.observability import measure
from PHOEBUS.llm_health import skip as llm_skip

try:
    from PHOEBUS.config import arena_client, ARENA_MODEL
    _arena_deep_model = os.getenv("ARENA_DEEP_MODEL", ARENA_MODEL).strip() or ARENA_MODEL
except Exception:
    arena_client = None
    _arena_deep_model = ""


# ── Config ────────────────────────────────────────────────────────────────
CAMERA_PC_INDEX = int(os.getenv("PHOEBUS_CAMERA_PC_INDEX", "0"))
CAMERA_PHONE_TIMEOUT = float(os.getenv("PHOEBUS_CAMERA_PHONE_TIMEOUT", "8"))
CAMERA_IP_URL = os.getenv("PHOEBUS_CAMERA_IP_URL", "").strip()


# ── Capture PC webcam ────────────────────────────────────────────────────

def _capture_pc_webcam_sync() -> Optional[bytes]:
    """Capture une frame depuis la webcam PC. Renvoie bytes JPEG ou None.
    Synchrone — à wrapper via asyncio.to_thread depuis le code async."""
    try:
        import cv2  # type: ignore
    except Exception as e:
        print(f"[CAM] OpenCV indisponible : {e}")
        return None

    cap = None
    try:
        cap = cv2.VideoCapture(CAMERA_PC_INDEX)
        if not cap.isOpened():
            print(f"[CAM] Impossible d'ouvrir la webcam (index={CAMERA_PC_INDEX}).")
            return None

        # On lit quelques frames pour laisser l'autoexposition se stabiliser.
        # Sans ça la première frame est souvent noire/sous-exposée.
        for _ in range(4):
            cap.read()

        ok, frame = cap.read()
        if not ok or frame is None:
            print("[CAM] Capture frame impossible.")
            return None

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None
        return bytes(buf)
    except Exception as e:
        print(f"[CAM] Erreur capture PC : {e}")
        return None
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass


async def capturer_pc_webcam() -> Optional[bytes]:
    """Capture asynchrone de la webcam PC. None si indisponible."""
    async with measure("camera.pc"):
        return await asyncio.to_thread(_capture_pc_webcam_sync)


# ── Capture caméra IP (snapshot HTTP ou flux RTSP/MJPEG via OpenCV) ─────

def _capture_ip_camera_sync(url: str) -> Optional[bytes]:
    if not url:
        return None
    # Cas 1 : URL HTTP renvoyant directement une image (snapshot.jpg).
    if url.startswith(("http://", "https://")):
        try:
            r = requests.get(url, timeout=4, stream=True)
            r.raise_for_status()
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "image/" in ctype:
                return r.content
            # MJPEG : on extrait la première frame du stream.
            if "multipart" in ctype or "x-mixed-replace" in ctype:
                buf = b""
                start = b"\xff\xd8"  # JPEG SOI
                end = b"\xff\xd9"    # JPEG EOI
                for chunk in r.iter_content(8192):
                    buf += chunk
                    s = buf.find(start)
                    e = buf.find(end, s + 2) if s != -1 else -1
                    if s != -1 and e != -1:
                        return buf[s : e + 2]
                    if len(buf) > 3 * 1024 * 1024:
                        break
        except Exception as e:
            print(f"[CAM] HTTP snapshot KO : {e}")
            return None

    # Cas 2 : URL RTSP / file → on tente OpenCV.
    try:
        import cv2  # type: ignore
        cap = cv2.VideoCapture(url)
        try:
            if not cap.isOpened():
                return None
            ok, frame = cap.read()
            if not ok or frame is None:
                return None
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return bytes(buf) if ok else None
        finally:
            cap.release()
    except Exception as e:
        print(f"[CAM] OpenCV IP cam KO : {e}")
        return None


async def capturer_ip_camera(url: Optional[str] = None) -> Optional[bytes]:
    target = (url or CAMERA_IP_URL).strip()
    if not target:
        return None
    async with measure("camera.ip"):
        return await asyncio.to_thread(_capture_ip_camera_sync, target)


# ── Capture caméra du téléphone via WebSocket ──────────────────────────

async def capturer_telephone(facing: str = "environment") -> Optional[bytes]:
    """Demande au client mobile authentifié de capturer une frame caméra.

    `facing` : "environment" (caméra arrière, défaut) ou "user" (selfie).

    Renvoie bytes JPEG ou None si aucun mobile n'est connecté ou timeout.
    """
    recipients = state.get_authenticated_clients()
    # Filtre : on cible préférentiellement les clients mobile_app si l'info
    # est disponible. Sinon on broadcaste à tous les clients authentifiés.
    targets = []
    for ws in recipients:
        meta = state.CLIENT_META.get(ws, {}) or {}
        if meta.get("client_type") == "mobile_app":
            targets.append(ws)
    if not targets:
        targets = list(recipients)
    if not targets:
        print("[CAM] Aucun client connecté pour capturer la caméra du téléphone.")
        return None

    req_id = str(uuid.uuid4())
    fut = asyncio.get_event_loop().create_future()
    state.PENDING_PHONE_CAPTURES[req_id] = fut

    import json as _json
    msg = _json.dumps({
        "action": "request_phone_camera",
        "id": req_id,
        "facing": facing,
    })

    async with measure("camera.phone"):
        await asyncio.gather(
            *[ws.send(msg) for ws in targets], return_exceptions=True
        )
        try:
            b64 = await asyncio.wait_for(fut, timeout=CAMERA_PHONE_TIMEOUT)
        except asyncio.TimeoutError:
            state.PENDING_PHONE_CAPTURES.pop(req_id, None)
            print(f"[CAM] Téléphone n'a pas répondu sous {CAMERA_PHONE_TIMEOUT}s.")
            return None

    if not b64:
        return None
    try:
        # Le client envoie typiquement "data:image/jpeg;base64,XXXX"
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        return base64.b64decode(b64)
    except Exception as e:
        print(f"[CAM] Décodage base64 téléphone KO : {e}")
        return None


# ── Capture d'écran TV (via ADB) ──────────────────────────────────────────

async def capturer_tv_ecran() -> Optional[bytes]:
    """Capture l'écran de la TV via ADB. Renvoie bytes JPEG ou None."""
    import subprocess
    from PHOEBUS.config import ADB_PATH
    from PHOEBUS.skills.network_skills import _load_devices
    
    # Trouver l'IP de la TV
    device_ip = ""
    devices = _load_devices()
    for dinfo in devices.values():
        if dinfo.get("type") == "android_tv":
            device_ip = dinfo.get("ip", "")
            break
            
    if not device_ip:
        return None

    target = f"{device_ip}:5555"
    try:
        # On s'assure d'être connecté
        await asyncio.to_thread(subprocess.run, [ADB_PATH, "connect", target], capture_output=True, timeout=3)
        
        # Capture vers un fichier temporaire sur le Mac (plus simple que le pipe binaire ADB)
        temp_file = "PHOEBUS_tv_cap.png"
        
        # screencap vers stdout est souvent corrompu sur certains Android (LF vs CRLF)
        # donc on fait un screencap -> file -> pull -> delete
        cmd_cap = [ADB_PATH, "-s", target, "shell", "screencap", "-p", "/sdcard/phoebus_cap.png"]
        await asyncio.to_thread(subprocess.run, cmd_cap, capture_output=True, timeout=5)
        
        cmd_pull = [ADB_PATH, "-s", target, "pull", "/sdcard/phoebus_cap.png", temp_file]
        await asyncio.to_thread(subprocess.run, cmd_pull, capture_output=True, timeout=5)
        
        if not os.path.exists(temp_file):
            return None
            
        with open(temp_file, "rb") as f:
            img_data = f.read()
            
        os.remove(temp_file)
        
        # Conversion PNG -> JPG (plus léger pour le LLM)
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(img_data))
            out = io.BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=85)
            return out.getvalue()
        except Exception:
            return img_data # Retourne le PNG si PIL échoue
            
    except Exception as e:
        print(f"[CAM] Erreur capture TV ADB : {e}")
        return None


# ── Analyse de l'image via LLM Vision ────────────────────────────────────

async def analyser_image(image_bytes: bytes, question: str = "Décris ce que tu vois en une phrase.",
                         use_arena_for_complex: bool = False) -> str:
    """Envoie l'image au LLM vision et renvoie la réponse texte.

    Préfère Gemini Vision (rapide, gratuit). Pour les analyses fines (OCR
    de documents, détails subtils), bascule sur LMArena Claude si
    `use_arena_for_complex=True` ou si Gemini est en cooldown.
    """
    if not image_bytes:
        return "Je n'ai pas pu obtenir d'image."

    # Tentative LMArena (Claude/GPT-4o vision) si demandé et disponible.
    # Accède aux modèles puissants gratuitement via le bridge LMArena.
    if (use_arena_for_complex or llm_skip("gemini")) and arena_client is not None:
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            data_url = f"data:image/jpeg;base64,{b64}"
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ]
            async with measure("vision.arena"):
                completion = await asyncio.to_thread(
                    arena_client.chat.completions.create,
                    model=_arena_deep_model,
                    messages=messages,
                    temperature=0.4,
                    timeout=20,
                )
            if completion and completion.choices:
                rep = (completion.choices[0].message.content or "").strip()
                if rep:
                    return rep
        except Exception as e:
            print(f"[VISION] Arena KO ({e}), repli Gemini.")

    # Gemini Vision (par défaut).
    if not client or not types or llm_skip("gemini"):
        return "Le module de vision est temporairement indisponible."

    try:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        contents = [types.Content(role="user", parts=[image_part, types.Part(text=question)])]
        async with measure("vision.gemini"):
            for model_name in MODELS_LIST:
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name,
                            config=types.GenerateContentConfig(temperature=0.4),
                            contents=contents,
                        ),
                        timeout=12.0,
                    )
                    if response.text:
                        return response.text.strip()
                except Exception:
                    continue
        return "Je n'ai rien pu déduire de l'image."
    except Exception as e:
        return f"Analyse vision impossible : {e}"
