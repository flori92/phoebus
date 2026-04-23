# jarvis/state.py
"""État global mutable partagé entre les modules JARVIS.

Centralise les connexions WebSocket, les flags et les fonctions de diffusion.
Tous les modules qui doivent lire/écrire de l'état partagé importent depuis ici.
"""
import asyncio
import json
from datetime import datetime

from jarvis.config import types, WS_AUTH_REQUIRED

# ── Connexions WebSocket ────────────────────────────────────────────────────
CONNECTED_CLIENTS = set()
AUTHENTICATED_CLIENTS = set()
CLIENT_META = {}
PENDING_SCREEN_CAPTURES = {}

# ── Flags globaux ───────────────────────────────────────────────────────────
interface_deja_connectee = False
_skip_pc_audio = False
PENDING_CONFIRMATION = None

is_listening  = False
is_speaking   = False
is_thinking   = False
speak_volume  = 0.0

jarvis_actif    = False
dernier_message = 0.0
STOP_PARLER     = False

MODE_IRON_MAN = False
VIDEO_LANCEE  = False

dossier_courant    = None
dernier_doc_id     = None
dernier_doc_titre  = None

# ── Historique de conversation ──────────────────────────────────────────────
historique = []


def ajouter_historique(role, texte):
    if not types:
        return
    historique.append(types.Content(role=role, parts=[types.Part(text=texte)]))


# ── Fonctions WebSocket partagées ───────────────────────────────────────────

def get_authenticated_clients():
    return {ws for ws in CONNECTED_CLIENTS
            if (not WS_AUTH_REQUIRED or ws in AUTHENTICATED_CLIENTS)}


def register_authenticated_client(websocket, data=None):
    AUTHENTICATED_CLIENTS.add(websocket)
    CLIENT_META[websocket] = {
        "client_type": (data or {}).get("client_type", "unknown"),
        "client_name": (data or {}).get("client_name", ""),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }


def unregister_client(websocket):
    meta = CLIENT_META.get(websocket, {})
    CONNECTED_CLIENTS.discard(websocket)
    AUTHENTICATED_CLIENTS.discard(websocket)
    CLIENT_META.pop(websocket, None)
    return meta


async def send_ws_json(websocket, payload):
    try:
        await websocket.send(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        print(f"[WEB] Envoi websocket impossible : {e}")


async def send_web_state(state):
    recipients = get_authenticated_clients()
    if recipients:
        message = json.dumps({"action": "set_state", "state": state})
        await asyncio.gather(*[ws.send(message) for ws in recipients],
                             return_exceptions=True)


async def send_web_volume(volume):
    recipients = get_authenticated_clients()
    if recipients:
        message = json.dumps({"action": "set_volume", "volume": round(volume, 3)})
        await asyncio.gather(*[ws.send(message) for ws in recipients],
                             return_exceptions=True)
