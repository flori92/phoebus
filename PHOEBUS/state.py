# PHOEBUS/state.py
"""État global mutable partagé entre les modules PHOEBUS.

Centralise les connexions WebSocket, les flags et les fonctions de diffusion.
Tous les modules qui doivent lire/écrire de l'état partagé importent depuis ici.
"""

import asyncio
import json
import os
import re
import time as _time
from collections import deque
from datetime import datetime

from PHOEBUS.config import types, WS_AUTH_REQUIRED

# ── Connexions WebSocket ────────────────────────────────────────────────────
CONNECTED_CLIENTS = set()
AUTHENTICATED_CLIENTS = set()
CLIENT_META = {}
PENDING_SCREEN_CAPTURES = {}
# Captures caméra téléphone en attente : {req_id: asyncio.Future}
PENDING_PHONE_CAPTURES = {}
# Commandes téléphone en attente de réponse : {req_id: asyncio.Future}
PENDING_PHONE_COMMANDS = {}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# ── Flags globaux ───────────────────────────────────────────────────────────
interface_deja_connectee = False
_skip_pc_audio = False
PENDING_CONFIRMATION = None

is_listening = False
is_speaking = False
is_thinking = False
is_proactive = False
speak_volume = 0.0

PHOEBUS_actif = False
dernier_message = 0.0
STOP_PARLER = False

MODE_IRON_MAN = False
VIDEO_LANCEE = False

# ── Mode Interprète (Traduction Live) ──────────────────────────────
INTERPRETE_ACTIF = False
INTERPRETE_LANGUE_CIBLE = "anglais"

# ── Mode Conversation Naturelle ───────────────────────────────────
# ─────────
# Pendant cette fenêtre, le mot-clé "PHOEBUS" n'est plus requis : on enchaîne
# naturellement avec des échanges suivis, comme avec un humain.
CONVERSATION_WINDOW_SECONDS = _float_env("PHOEBUS_CONVERSATION_WINDOW_SECONDS", 45.0)
conversation_deadline_ts = 0.0

# ── Activité utilisateur / silence ─────────────────────────────────────────
# Suivi du dernier signe de vie de l'utilisateur (parole, requête web, click...).
last_user_activity_ts = 0.0
silence_ping_sent = False  # Évite de repinger en boucle après un long silence.


# ── Barge-in (interruption de PHOEBUS par la voix) ─────────────────────────
BARGE_IN_THRESHOLD = _int_env("PHOEBUS_BARGE_IN_THRESHOLD", 4500)
BARGE_IN_CONSECUTIVE_CHUNKS = _int_env("PHOEBUS_BARGE_IN_CONSECUTIVE_CHUNKS", 4)
BARGE_IN_CONVERSATION_SECONDS = _float_env(
    "PHOEBUS_BARGE_IN_CONVERSATION_SECONDS",
    CONVERSATION_WINDOW_SECONDS,
)

# ── Anti-Écho (PHOEBUS ne se parle pas à lui-même) ─────────────────────────
last_PHOEBUS_speech = ""  # Texte exact du dernier bloc prononcé
last_speech_timestamp = 0.0  # Heure de fin de parole
current_PHOEBUS_speech = ""  # Texte en cours de prononciation
speech_started_timestamp = 0.0

# ── Tâches de fond (actions longues non bloquantes) ───────────────────────
background_tasks = {}  # {id: {"task": asyncio.Task, "label": str, "started": ts}}
_background_seq = 0

# ── Anti-écho acoustique ──────────────────────────────────────────────────
# Quand PHOEBUS parle, le micro capte SA propre voix via les enceintes. Sans
# protection, Whisper/Google transcrivent ces retours et PHOEBUS se répond
# à lui-même → boucle infinie. Deux couches :
#   (1) un délai de refroidissement après la parole — le temps que l'audio
#       résiduel se dissipe et que le buffer du micro se vide.
#   (2) une mémoire glissante des dernières phrases dites : toute
#       transcription qui ressemble fortement à l'une d'elles est rejetée.
POST_SPEAK_COOLDOWN_S = 1.4
post_speak_until_ts = 0.0
recent_PHOEBUS_utterances: deque = deque(maxlen=10)


def _normalize_for_echo(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def mark_spoke(texte: str) -> None:
    """À appeler à la fin de parler() : démarre le cooldown et enregistre
    ce qu'on vient de dire pour détecter un éventuel retour acoustique."""
    global post_speak_until_ts
    post_speak_until_ts = _time.time() + POST_SPEAK_COOLDOWN_S
    norm = _normalize_for_echo(texte)
    if norm and len(norm) >= 3:
        recent_PHOEBUS_utterances.append(norm)


def in_post_speak_cooldown() -> bool:
    return _time.time() < post_speak_until_ts


def looks_like_own_echo(texte_transcript: str) -> bool:
    """Vrai si la transcription ressemble à une phrase qu'on vient de dire.

    Heuristiques :
    - pendant le cooldown post-parole, une transcription courte (<30 car.)
      est très probablement un morceau d'écho ;
    - sinon, comparaison de recouvrement avec les 10 dernières utterances :
      inclusion substring OU >55 % de tokens partagés.
    """
    if not texte_transcript:
        return False
    t_norm = _normalize_for_echo(texte_transcript)
    if not t_norm:
        return False

    if in_post_speak_cooldown() and len(t_norm) < 30:
        return True

    t_tokens = set(t_norm.split())
    for utt in recent_PHOEBUS_utterances:
        if t_norm in utt or (len(t_norm) >= 10 and utt in t_norm):
            return True
        u_tokens = set(utt.split())
        if t_tokens and u_tokens:
            inter = t_tokens & u_tokens
            denom = min(len(t_tokens), len(u_tokens))
            if denom and len(inter) / denom > 0.55 and len(inter) >= 2:
                return True
    return False


dossier_courant = None
dernier_doc_id = None
dernier_doc_titre = None

# ── Historique de conversation ──────────────────────────────────────────────
historique = []


def ajouter_historique(role, texte):
    if not types:
        return
    historique.append(types.Content(role=role, parts=[types.Part(text=texte)]))


# ── Helpers Conversation Naturelle ─────────────────────────────────────────


def extend_conversation(seconds=None):
    """Ouvre ou prolonge la fenêtre "on est en train de discuter".
    Tant qu'elle est active, le STT traite la parole sans exiger "PHOEBUS"."""
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


def cancel_background_task(tid):
    info = background_tasks.get(int(tid)) if tid is not None else None
    if not info:
        return False
    task = info.get("task")
    if task and not task.done():
        task.cancel()
    background_tasks.pop(int(tid), None)
    return True


def active_background_tasks():
    # Nettoyage opportuniste des tâches terminées.
    finished = [tid for tid, info in background_tasks.items() if info["task"].done()]
    for tid in finished:
        background_tasks.pop(tid, None)
    return dict(background_tasks)


# ── Fonctions WebSocket partagées ───────────────────────────────────────────


def get_authenticated_clients():
    return {ws for ws in CONNECTED_CLIENTS if (not WS_AUTH_REQUIRED or ws in AUTHENTICATED_CLIENTS)}


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
        await asyncio.gather(*[ws.send(message) for ws in recipients], return_exceptions=True)


async def send_web_volume(volume):
    recipients = get_authenticated_clients()
    if recipients:
        message = json.dumps({"action": "set_volume", "volume": round(volume, 3)})
        await asyncio.gather(*[ws.send(message) for ws in recipients], return_exceptions=True)


async def send_web_expression(text, utterance_id=None):
    recipients = get_authenticated_clients()
    if recipients and text:
        payload = {"action": "PHOEBUS_expression", "text": text}
        if utterance_id:
            payload["id"] = utterance_id
        message = json.dumps(payload, ensure_ascii=False)
        await asyncio.gather(*[ws.send(message) for ws in recipients], return_exceptions=True)


async def send_web_lipsync(frames, utterance_id=None, backend=None):
    recipients = get_authenticated_clients()
    if recipients and frames:
        payload = {"action": "PHOEBUS_lipsync", "frames": frames}
        if utterance_id:
            payload["id"] = utterance_id
        if backend:
            payload["backend"] = backend
        message = json.dumps(payload, ensure_ascii=False)
        await asyncio.gather(*[ws.send(message) for ws in recipients], return_exceptions=True)


async def broadcast(payload):
    """Diffuse un message JSON à tous les clients authentifiés."""
    recipients = get_authenticated_clients()
    if recipients:
        message = json.dumps(payload, ensure_ascii=False)
        await asyncio.gather(*[ws.send(message) for ws in recipients], return_exceptions=True)

# ── Commandes pour iOS Shortcut (Focus Mode Hack) ──
IOS_PENDING_COMMANDS = []
