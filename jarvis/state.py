# jarvis/state.py
"""État global mutable partagé entre les modules JARVIS.

Centralise les connexions WebSocket, les flags et les fonctions de diffusion.
Tous les modules qui doivent lire/écrire de l'état partagé importent depuis ici.
"""
import asyncio
import json
import time as _time
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

# ── Mode Conversation Naturelle ────────────────────────────────────────────
# Pendant cette fenêtre, le mot-clé "jarvis" n'est plus requis : on enchaîne
# naturellement avec des échanges suivis, comme avec un humain.
CONVERSATION_WINDOW_SECONDS = 45
conversation_deadline_ts = 0.0

# ── Activité utilisateur / silence ─────────────────────────────────────────
# Suivi du dernier signe de vie de l'utilisateur (parole, requête web, click...).
last_user_activity_ts = 0.0
silence_ping_sent = False  # Évite de repinger en boucle après un long silence.

# ── Barge-in (interruption de Jarvis par la voix) ─────────────────────────
BARGE_IN_THRESHOLD = 2200  # RMS au-dessus duquel on considère que l'utilisateur parle.
BARGE_IN_CONSECUTIVE_CHUNKS = 3  # Nb de chunks consécutifs au-dessus du seuil.

# ── Tâches de fond (actions longues non bloquantes) ───────────────────────
background_tasks = {}  # {id: {"task": asyncio.Task, "label": str, "started": ts}}
_background_seq = 0

dossier_courant    = None
dernier_doc_id     = None
dernier_doc_titre  = None

# ── Historique de conversation ──────────────────────────────────────────────
historique = []


def ajouter_historique(role, texte):
    if not types:
        return
    historique.append(types.Content(role=role, parts=[types.Part(text=texte)]))


# ── Helpers Conversation Naturelle ─────────────────────────────────────────

def extend_conversation(seconds=None):
    """Ouvre ou prolonge la fenêtre "on est en train de discuter".
    Tant qu'elle est active, le STT traite la parole sans exiger "jarvis"."""
    global conversation_deadline_ts
    dur = seconds if seconds is not None else CONVERSATION_WINDOW_SECONDS
    conversation_deadline_ts = _time.time() + dur


def is_in_conversation():
    return _time.time() < conversation_deadline_ts


def end_conversation():
    global conversation_deadline_ts, silence_ping_sent
    conversation_deadline_ts = 0.0
    silence_ping_sent = False


def mark_user_activity():
    global last_user_activity_ts, silence_ping_sent
    last_user_activity_ts = _time.time()
    silence_ping_sent = False


def seconds_since_user_activity():
    if last_user_activity_ts == 0.0:
        return None
    return _time.time() - last_user_activity_ts


# ── Helpers tâches de fond ─────────────────────────────────────────────────

def register_background_task(task, label):
    global _background_seq
    _background_seq += 1
    tid = _background_seq
    background_tasks[tid] = {
        "task": task,
        "label": label,
        "started": _time.time(),
    }
    return tid


def drop_background_task(tid):
    background_tasks.pop(tid, None)


def active_background_tasks():
    # Nettoyage opportuniste des tâches terminées.
    finished = [tid for tid, info in background_tasks.items() if info["task"].done()]
    for tid in finished:
        background_tasks.pop(tid, None)
    return dict(background_tasks)


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
