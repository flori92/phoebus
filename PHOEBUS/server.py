# PHOEBUS/server.py
"""Serveur WebSocket, HTTP mobile et boucle principale de PHOEBUS."""
import json
import time
import asyncio
import threading
import http.server
import socketserver
import concurrent.futures
import hmac
import hashlib
import os
import sys

from PHOEBUS.config import (
    websockets, sr, DEFAULT_WS_PORT, DEFAULT_MOBILE_PORT, MOBILE_DIR,
    PHOEBUS_WS_TOKEN, WS_AUTH_REQUIRED, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    PHOEBUS_WAKE_ENABLED,
)
import PHOEBUS.state as state
from PHOEBUS.security import audit_log, sanitize_action_data
from PHOEBUS.desktop import executer_action_pc
from PHOEBUS.ai import demander_ia, demander_ia_vision, demander_ia_stream
from PHOEBUS.actions import traiter_reponse_ia
from PHOEBUS.voice import parler, monitor_claps
from PHOEBUS.stt_backends import get_backend as get_stt_backend
from PHOEBUS.clarify import transcription_incertaine
from PHOEBUS import proactive

# Imports optionnels
try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
    _TELEGRAM_AVAILABLE = True
except ImportError:
    _TELEGRAM_AVAILABLE = False

# Imports optionnels des nouveaux modules
try:
    from PHOEBUS import wake_word as _wake_word_module
    _WAKE_WORD_AVAILABLE = True
except ImportError:
    _WAKE_WORD_AVAILABLE = False

try:
    from PHOEBUS.multi_user import identifier_speaker, MULTI_USER_ENABLED
except ImportError:
    identifier_speaker = None
    MULTI_USER_ENABLED = False

try:
    from PHOEBUS.memory_timeline import enregistrer_evenement as _timeline_evt
except ImportError:
    _timeline_evt = None


# ── Sécurité WebSocket ─────────────────────────────────────────────────────

def verify_token(provided_token):
    # Authentification désactivée par l'utilisateur
    return True


def _payload_text(data: dict, *keys: str) -> str:
    """Retourne le premier champ texte non vide d'une charge JSON."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# ── Gestionnaire WebSocket ─────────────────────────────────────────────────

async def ws_handler(websocket):
    if not websockets:
        return

    state.CONNECTED_CLIENTS.add(websocket)
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    
    print(f"[WEB] Nouvelle connexion WebSocket depuis {client_ip}")

    if WS_AUTH_REQUIRED:
        await state.send_ws_json(websocket, {"action": "auth_required"})
    else:
        state.register_authenticated_client(websocket, {"client_type": "unknown", "client_name": "auto-auth"})
        await state.send_ws_json(websocket, {"action": "auth_ok"})
        if not state.interface_deja_connectee:
            await parler("Interface connectée.", keep_conversation=False)
            state.interface_deja_connectee = True

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                # On accepte 'action' ou 'type' pour la compatibilité
                action = data.get("action") or data.get("type")
                
                # --- Authentification ---
                if action == "auth":
                    token = data.get("token", "")
                    client_type = data.get("client_type", "unknown")
                    if verify_token(token):
                        state.register_authenticated_client(websocket, data)
                        await state.send_ws_json(websocket, {"action": "auth_ok"})
                        audit_log("ws_auth_success", ip=client_ip, client_type=client_type)
                        if client_type == "web_dashboard" and not state.interface_deja_connectee:
                            await parler("Interface web authentifiée.", keep_conversation=False)
                            state.interface_deja_connectee = True
                        elif client_type == "mobile_app":
                            await parler("Satellite mobile authentifié.", keep_conversation=False)
                    else:
                        await state.send_ws_json(websocket, {"action": "auth_failed"})
                        audit_log("ws_auth_failed", ip=client_ip, client_type=client_type)
                    continue

                if WS_AUTH_REQUIRED and websocket not in state.AUTHENTICATED_CLIENTS:
                    await state.send_ws_json(websocket, {"action": "auth_required"})
                    continue

                # --- Actions authentifiées ---
                safe_data = sanitize_action_data(data)
                if action not in {"audio_chunk", "screen_capture_result", "pong", "audio_level"}:
                    audit_log("ws_command_received", ip=client_ip, **safe_data)

                if action == "ping":
                    await state.send_ws_json(websocket, {"action": "pong"})
                    
                elif action == "test_vocal":
                    await parler("Test vocal depuis l'interface web.")
                    
                elif action == "PHOEBUS_parler":
                    txt = _payload_text(data, "text", "message", "command", "commande", "query")
                    if txt: await parler(txt)
                    
                elif action == "stop_parler" or action == "stop_audio":
                    state.STOP_PARLER = True
                    
                elif action == "demander_ia" or action == "mobile_command":
                    question = _payload_text(data, "text", "message", "command", "commande", "query", "question")
                    if question:
                        reponse_texte = await executer_commande_generique(question, source="web")
                        if reponse_texte:
                            await state.send_ws_json(
                                websocket,
                                {"action": "PHOEBUS_response", "text": reponse_texte},
                            )

                elif action == "demander_ia_vision":
                    question = _payload_text(data, "text", "message", "question", "query")
                    img_b64 = data.get("image", "")
                    if question and img_b64:
                        state.extend_conversation()
                        state.mark_user_activity()
                        rep = await demander_ia_vision(question, img_b64)
                        if not await traiter_reponse_ia(rep):
                            await parler(rep)
                        state.extend_conversation()
                            
                elif action == "action_pc":
                    cmd = _payload_text(data, "commande", "command", "text", "message", "query")
                    res = executer_action_pc(cmd)
                    if res: await parler(res)
                    
                elif action == "set_skip_audio":
                    state._skip_pc_audio = bool(data.get("value", False))
                    print(f"[WEB] Skip PC Audio : {state._skip_pc_audio}")
                    
                elif action == "screen_capture_result":
                    req_id = data.get("id")
                    img_b64 = data.get("image")
                    if req_id in state.PENDING_SCREEN_CAPTURES:
                        fut = state.PENDING_SCREEN_CAPTURES.pop(req_id)
                        if not fut.done():
                            fut.set_result(img_b64)

                elif action == "phone_camera_result":
                    # Frame caméra téléphone retournée par mobile/app.js.
                    req_id = data.get("id")
                    img_b64 = data.get("image")
                    if req_id in state.PENDING_PHONE_CAPTURES:
                        fut = state.PENDING_PHONE_CAPTURES.pop(req_id)
                        if not fut.done():
                            fut.set_result(img_b64)

                elif action == "audio_chunk":
                    pass

            except json.JSONDecodeError:
                print(f"[WEB] Message JSON invalide : {message[:50]}...")
            except Exception as e:
                print(f"[WEB] Erreur traitement WS : {e}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        meta = state.unregister_client(websocket)
        audit_log("ws_client_disconnected", ip=client_ip, **meta)
        if meta.get("client_type") == "web_dashboard" and state.interface_deja_connectee:
            if not any(m.get("client_type") == "web_dashboard" for m in state.CLIENT_META.values()):
                state.interface_deja_connectee = False
                print("[WEB] Interface deconnectee.")


async def start_websocket_server():
    if not websockets:
        print("[WEB] websockets non installe.")
        return
    port = DEFAULT_WS_PORT
    while True:
        try:
            # On utilise le port fixe 8765 pour être synchro avec le frontend.
            print(f"[WEB] Serveur WebSocket sur ws://0.0.0.0:{port}")
            if WS_AUTH_REQUIRED:
                print("[WEB] AUTHENTIFICATION REQUISE (Token actif).")
            async with websockets.serve(ws_handler, "0.0.0.0", port):
                await asyncio.Future()
        except Exception as e:
            print(f"[WEB] Erreur WebSocket (port {DEFAULT_WS_PORT} probablement occupé) : {e}")
            await asyncio.sleep(3)


# ── Globaux ────────────────────────────────────────────────────────────────

main_loop = None


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


COMMAND_REPLY_TIMEOUT = _float_env("PHOEBUS_COMMAND_REPLY_TIMEOUT", 10.0)
AI_COMMAND_TIMEOUT = _float_env("PHOEBUS_AI_COMMAND_TIMEOUT", 35.0)


async def _parler_safe(texte: str, keep_conversation: bool = True) -> None:
    try:
        await parler(texte, keep_conversation=keep_conversation)
    except Exception as e:
        print(f"[VOICE] parole ignorée après erreur : {e}")


class _SpeechQueue:
    """File de parole non bloquante: le LLM continue pendant que PHOEBUS parle."""

    def __init__(self):
        self._queue = asyncio.Queue()
        self._task = None

    async def say(self, texte: str) -> None:
        if not texte or not texte.strip():
            return
        if self._task is None:
            self._task = asyncio.create_task(self._run())
        self._queue.put_nowait(texte)

    async def _run(self) -> None:
        while True:
            texte = await self._queue.get()
            if texte is None:
                self._queue.task_done()
                return
            try:
                await _parler_safe(texte)
            finally:
                self._queue.task_done()

    def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._queue.put_nowait(None)


async def executer_commande_generique(texte: str, source: str = "voix", metadata: dict = None) -> str:
    """Exécute une commande texte et renvoie la réponse textuelle finale."""
    if not texte: return ""
    
    state.mark_user_activity()
    meta_str = ""
    if metadata:
        m = metadata
        meta_str = f" [Batt: {m.get('battery')}% | Loc: {m.get('location')} | Focus: {m.get('focus')}]"
    
    print(f"[{source.upper()}{meta_str}] {texte}")
    
    # On injecte les métadonnées dans le contexte pour l'IA
    contexte_ios = ""
    if metadata:
        contexte_ios = (
            f"\n[INFO IPHONE] Batterie: {metadata.get('battery')}% | "
            f"Position: {metadata.get('location')} | "
            f"Mode de concentration: {metadata.get('focus')}\n"
        )

    query_enrichie = contexte_ios + texte

    # Pour collecter la réponse textuelle
    full_text_parts = []

    spoken = {"v": False}
    speech = _SpeechQueue()

    async def _on_sentence(s):
        nonlocal spoken
        spoken["v"] = True
        full_text_parts.append(s)
        await speech.say(s)

    try:
        # On utilise le streaming pour la réactivité.
        # demander_ia_stream renvoie le texte COMPLET accumulé.
        rep_finale_ia = await asyncio.wait_for(
            demander_ia_stream(query_enrichie, on_sentence=_on_sentence),
            timeout=AI_COMMAND_TIMEOUT,
        )

        # Cas 1 : C'est du JSON (Action technique)
        if "{" in (rep_finale_ia or "") and "}" in (rep_finale_ia or ""):
            await traiter_reponse_ia(rep_finale_ia)
            # On renvoie une confirmation courte si c'est une commande muette.
            return "Action exécutée, Monsieur." if not spoken["v"] else " ".join(full_text_parts)

        # Cas 2 : Réponse textuelle normale
        if not spoken["v"] and rep_finale_ia:
            # Si le streaming a échoué mais qu'on a une réponse brute.
            if not await traiter_reponse_ia(rep_finale_ia):
                await speech.say(rep_finale_ia)
                return rep_finale_ia

        return " ".join(full_text_parts).strip() or rep_finale_ia or ""

    except asyncio.TimeoutError:
        msg = "Je réfléchis encore, Floriace. La réponse vocale arrive dès que le cerveau se débloque."
        await speech.say(msg)
        return msg
    except Exception as e:
        print(f"[COMMANDE] Erreur traitement {source} : {e}")
        msg = "J'ai eu un raté interne, Floriace, mais je reste opérationnel."
        await speech.say(msg)
        return msg
    finally:
        # On reste à l'écoute après une commande externe et on laisse la file
        # audio terminer en arrière-plan.
        state.extend_conversation()
        speech.close()

# ── Serveur Mobile (HTTP) ──────────────────────────────────────────────────

class MobileHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(MOBILE_DIR), **kwargs)
        
    def log_message(self, format, *args):
        pass
        
    def do_GET(self):
        """Page de test + endpoints d'observabilité."""
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "PHOEBUS Online", "ip": self.client_address[0]}).encode())
            return
        # ── Observabilité ────────────────────────────────────────────────
        if self.path == '/metrics' or self.path.startswith('/metrics?'):
            from PHOEBUS.observability import render_json
            body = render_json().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/dashboard' or self.path.startswith('/dashboard?'):
            from PHOEBUS.observability import render_html
            body = render_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/health' or self.path.startswith('/health?'):
            from PHOEBUS.llm_health import status as llm_status
            body = json.dumps({
                "llm_cooldowns": llm_status(),
                "is_speaking": state.is_speaking,
                "is_thinking": state.is_thinking,
                "conversation": state.is_in_conversation(),
                "post_speak_cooldown": state.in_post_speak_cooldown(),
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        """Webhooks: Reçoit les événements HA ou les commandes iPhone."""
        # Sécurité basique via Token (on accepte Authorization ou authorization)
        auth_header = self.headers.get('Authorization') or self.headers.get('authorization', '')
        token_valid = True
        if WS_AUTH_REQUIRED:
            token_valid = (f"Bearer {PHOEBUS_WS_TOKEN}" == auth_header)

        if self.path == '/webhook/ha_event':
            # ... (code existant pour HA)
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                message = data.get("message", "")
                if message:
                    if main_loop:
                        asyncio.run_coroutine_threadsafe(parler(message, keep_conversation=False), main_loop)
                self.send_response(200)
                self.end_headers()
            except:
                self.send_response(400)
                self.end_headers()

        elif self.path.startswith('/webhook/command'):
            # Extraction du token depuis le header OU l'URL (?token=...)
            from urllib.parse import urlparse, parse_qs
            query = urlparse(self.path).query
            query_params = parse_qs(query)
            url_token = query_params.get('token', [None])[0]
            
            auth_header = self.headers.get('Authorization') or self.headers.get('authorization', '')
            provided_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header
            
            # Si Option A (WS_AUTH_REQUIRED=False), on accepte tout.
            # Sinon, on vérifie l'un des deux tokens fournis.
            final_auth_ok = True
            if WS_AUTH_REQUIRED:
                final_auth_ok = (provided_token == PHOEBUS_WS_TOKEN or url_token == PHOEBUS_WS_TOKEN)

            if not final_auth_ok:
                print(f"[WEBHOOK] Accès refusé pour {self.client_address[0]}")
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized: Token invalid or missing"}')
                return

            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length == 0:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Empty body"}')
                    return

                post_data = self.rfile.read(content_length).decode('utf-8')
                
                # Tentative de lecture JSON, sinon on prend le texte brut
                texte = ""
                metadata = {}
                try:
                    data = json.loads(post_data)
                    texte = _payload_text(data, "text", "command", "commande", "message", "query", "question")
                    metadata = {
                        "battery": data.get("battery", "Inconnue"),
                        "location": data.get("location", "Inconnue"),
                        "focus": data.get("focus", "Inconnu")
                    }
                except:
                    # Si ce n'est pas du JSON, on traite tout le body comme du texte
                    texte = post_data.strip()

                if texte:
                    if main_loop:
                        future = asyncio.run_coroutine_threadsafe(
                            executer_commande_generique(texte, source="ios", metadata=metadata), 
                            main_loop
                        )
                        def _log_future_error(done_future):
                            try:
                                done_future.result()
                            except Exception as exc:
                                print(f"[WEBHOOK] Commande arrière-plan KO : {exc}")

                        future.add_done_callback(_log_future_error)
                        try:
                            reponse_texte = future.result(timeout=COMMAND_REPLY_TIMEOUT)
                        except concurrent.futures.TimeoutError:
                            reponse_texte = (
                                "Je suis dessus, Floriace. "
                                "La réponse vocale arrive dès que le traitement se termine."
                            )
                    else:
                        reponse_texte = "Erreur : PHOEBUS Core non prêt."
                else:
                    reponse_texte = "Je n'ai pas reçu d'instruction, Monsieur."
                
                resp_payload = json.dumps({"status": "ok", "reply": reponse_texte}, ensure_ascii=False)
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(resp_payload.encode('utf-8'))
                
            except Exception as e:
                print(f"[WEBHOOK] Erreur : {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()


class ThreadingMobileServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_mobile_server():
    port = DEFAULT_MOBILE_PORT
    while True:
        try:
            with ThreadingMobileServer(("0.0.0.0", port), MobileHandler) as httpd:
                print(f"[MOBILE] App satellite dispo sur http://0.0.0.0:{port}")
                httpd.serve_forever()
        except Exception as e:
            print(f"[MOBILE] Serveur erreur (port {DEFAULT_MOBILE_PORT} occupé) : {e}")
            time.sleep(3)


# ── Écoute Vocale (STT) ────────────────────────────────────────────────────

def listen_and_process(main_loop):
    if not sr:
        print("[MIC] speech_recognition non installe.")
        return

    stt_name, stt_recognize = get_stt_backend()
    if stt_recognize is None:
        print("[MIC] Aucun back-end STT disponible.")
        return
    print(f"[MIC] Back-end STT actif : {stt_name}")

    r = sr.Recognizer()
    # On ajuste les paramètres pour être moins sensible au bruit de fond/silence
    r.pause_threshold = 1.1  # Temps de silence avant de valider une phrase
    r.non_speaking_duration = 0.5
    
    # Liste des hallucinations classiques de Whisper/Groq en cas de silence
    HALLUCINATIONS_STT = {
        "sous-titrage societe radio-canada",
        "sous-titrage",
        "societe radio-canada",
        "merci.",
        "merci",
        "visionne par",
        "veuillez vous abonner",
        "abonnez-vous",
        "merci d'avoir regarde",
        "transcription by",
        "merci beaucoup",
    }

    try:
        with sr.Microphone() as source:
            print("[MIC] Calibrage du bruit ambiant...")
            r.adjust_for_ambient_noise(source, duration=1.0)
            r.energy_threshold += 150
            print(f"[MIC] Prêt. Seuil d'énergie : {r.energy_threshold:.0f}")
            
            while True:
                try:
                    state.is_listening = True
                    asyncio.run_coroutine_threadsafe(state.send_web_state("listening"), main_loop)
                    
                    # On réduit le timeout pour boucler plus souvent et rester réactif
                    try:
                        audio = r.listen(source, timeout=5, phrase_time_limit=12)
                        print("[MIC] Audio capturé, transcription en cours...")
                    except sr.WaitTimeoutError:
                        # Timeout normal quand personne ne parle, on continue simplement
                        continue
                    
                    state.is_listening = False

                    if state.STOP_PARLER:
                        time.sleep(0.1)

                    try:
                        texte = stt_recognize(audio)
                        if not texte: raise sr.UnknownValueError()
                        
                        # ── Filtre anti-hallucination (Whisper/Groq) ───────────
                        from PHOEBUS.utils import normalize_text
                        this_clean = normalize_text(texte)
                        
                        if this_clean in HALLUCINATIONS_STT or len(this_clean) < 2:
                            # print(f"[MIC] Hallucination ignorée : \"{texte}\"")
                            asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                            continue

                        # ── Anti-écho secondaire : deque(10) des dernières
                        # utterances + cooldown post-parole 1.4s. Couche
                        # complémentaire de la détection ci-dessous (qui se
                        # base sur current/last_PHOEBUS_speech). Capte les
                        # cas où l'écho arrive juste après que parler() a
                        # vidé current_PHOEBUS_speech.
                        if state.looks_like_own_echo(texte):
                            print(f"[ECHO] Ignoré (auto-écho détecté) : {texte!r}")
                            asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                            continue

                        # ── Anti-Écho : PHOEBUS ne doit pas s'écouter lui-même ───
                        maintenant = time.time()
                        is_echo = False
                        recent_speech = (
                            state.is_speaking
                            or maintenant - state.last_speech_timestamp < 6.0
                            or maintenant - state.speech_started_timestamp < 10.0
                        )
                        echo_candidates = [
                            normalize_text(state.current_PHOEBUS_speech),
                            normalize_text(state.last_PHOEBUS_speech),
                        ]
                        for spoken_clean in echo_candidates:
                            if not spoken_clean:
                                continue
                            if spoken_clean in this_clean or this_clean in spoken_clean:
                                if recent_speech:
                                    is_echo = True
                                    break
                        
                        # 2. Si le texte est court et arrive juste après la fin de parole
                        if not is_echo and recent_speech:
                            if len(texte.split()) < 4:
                                is_echo = True
                                
                        if is_echo:
                            print(f"[MIC] Écho détecté et ignoré : \"{texte}\"")
                            asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                            continue

                    except sr.UnknownValueError:
                        asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                        continue
                    except Exception as e:
                        print(f"[MIC] STT {stt_name} a échoué : {e}")
                        asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                        continue

                    # On ne passe en 'thinking' que si on a vraiment du texte à traiter
                    asyncio.run_coroutine_threadsafe(state.send_web_state("thinking"), main_loop)
                    print(f"\n[VOUS] {texte}")

                    # ── Identification du speaker ───────────────────────────
                    speaker = "Floriace"
                    if MULTI_USER_ENABLED and identifier_speaker:
                        try:
                            speaker, confidence = identifier_speaker(audio)
                            print(f"[MULTIUSER] Speaker : {speaker} (confiance={confidence:.2f})")
                        except Exception:
                            pass

                    # Transcription trop courte / charabia → on redemande
                    # plutôt que d'halluciner une réponse.
                    if state.is_in_conversation() and transcription_incertaine(texte):
                        asyncio.run_coroutine_threadsafe(
                            parler("Pardon, je n'ai pas bien compris. Vous pouvez répéter ?"),
                            main_loop,
                        )
                        state.mark_user_activity()
                        continue

                    state.mark_user_activity()
                    texte_l = texte.lower()
                    # Liste élargie pour pallier les erreurs de transcription (phonétique proche)
                    WAKE_WORDS = ["PHOEBUS", "phébus", "fébus", "febus", "feubus", "rebus"]
                    wake = any(w.lower() in texte_l for w in WAKE_WORDS)
                    en_conversation = state.is_in_conversation()

                    if not (wake or en_conversation):
                        # Trop de bruit ambiant ? On réinitialise l'état et on continue.
                        state.is_listening = False
                        asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                        continue

                    # On nettoie le texte pour l'IA (enlever le mot d'appel s'il est au début)
                    cleaned_texte = texte
                    if wake and not en_conversation:
                        for w in WAKE_WORDS:
                            if texte_l.startswith(w.lower()):
                                cleaned_texte = texte[len(w):].strip(", ").strip()
                                break
                    
                    # "Mode iron man active" : raccourci direct.
                    if "mode iron man" in texte_l and "active" in texte_l:
                        state.MODE_IRON_MAN = True
                        asyncio.run_coroutine_threadsafe(parler("Mode Iron Man activé."), main_loop)
                        state.extend_conversation()
                        continue

                    # "stop / tais-toi / laisse tomber" pendant une conversation :
                    # on ferme la fenêtre pour redevenir discret.
                    if en_conversation and not wake and any(
                        m in texte_l for m in (
                            "laisse tomber", "laisse-moi", "tais-toi", "chut",
                            "stop phoebus", "merci phoebus", "c'est bon phoebus",
                        )
                    ):
                        state.end_conversation()
                        asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                        continue

                    # ── MODE INTERPRÈTE ── (Priorité haute)
                    if state.INTERPRETE_ACTIF:
                        from PHOEBUS.ai import traduire_live
                        async def wrap_traduction(txt, lang):
                            trad = await traduire_live(txt, lang)
                            await parler(trad, keep_conversation=True)
                        asyncio.run_coroutine_threadsafe(wrap_traduction(cleaned_texte, state.INTERPRETE_LANGUE_CIBLE), main_loop)
                        continue

                    asyncio.run_coroutine_threadsafe(executer_commande_generique(cleaned_texte, source="voix"), main_loop)
                            
                except sr.WaitTimeoutError:
                    if state.is_in_conversation():
                        print("[MIC] Silence détecté, PHOEBUS se remet en veille.")
                        state.end_conversation()
                    state.is_listening = False
                    asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                except sr.UnknownValueError:
                    state.is_listening = False
                    asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                except Exception as e:
                    print(f"[MIC] Erreur de reconnaissance : {e}")
                    state.is_listening = False
                    asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                    time.sleep(2)
    except Exception as e:
        print(f"[MIC] Impossible d'ouvrir le micro ou erreur fatale : {e}")
        time.sleep(3)
        print("[MIC] Relance de la boucle d'écoute...")
        return listen_and_process(main_loop)


# ── Bot Telegram ───────────────────────────────────────────────────────────

async def run_telegram_bot(main_loop):
    if not _TELEGRAM_AVAILABLE or not TELEGRAM_TOKEN:
        if TELEGRAM_TOKEN: print("[TELEGRAM] Librairie absente.")
        return

    print("[TELEGRAM] Démarrage du bot...")

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        # Sécurité : on ne répond qu'au propriétaire
        if not TELEGRAM_CHAT_ID:
            print(f"[TELEGRAM] Message reçu de ID: {chat_id}. Pour sécuriser, ajoutez TELEGRAM_CHAT_ID={chat_id} dans votre .env")
        elif chat_id != str(TELEGRAM_CHAT_ID):
            print(f"[TELEGRAM] Message ignoré de chat_id inconnu : {chat_id}")
            return

        user_text = update.message.text
        if not user_text: return

        # On exécute la commande via le cœur PHOEBUS et on attend la réponse
        future = asyncio.run_coroutine_threadsafe(
            executer_commande_generique(user_text, source="telegram"),
            main_loop
        )
        try:
            reponse_texte = future.result(timeout=30)
            await update.message.reply_text(reponse_texte or "Action exécutée, Monsieur.")
        except Exception as e:
            await update.message.reply_text(f"Désolé, une erreur est survenue : {e}")

    try:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        print("[TELEGRAM] Bot opérationnel.")
        # On garde la tâche en vie
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        print(f"[TELEGRAM] Erreur : {e}")


async def system_self_healing():
    """Surveille l'état du système et tente des réparations silencieuses."""
    while True:
        try:
            await asyncio.sleep(60) # Vérification toutes les minutes
            
            # Vérification de la santé des clients WebSocket
            from PHOEBUS.state import CONNECTED_CLIENTS, get_authenticated_clients
            if not CONNECTED_CLIENTS:
                # Si aucune interface n'est connectée pendant longtemps, 
                # on peut tenter un petit log de rappel
                pass
            
            # Ici on pourrait ajouter des tests de connectivité IA, etc.
            
        except Exception as e:
            print(f"[SELF-HEALING] Erreur lors du monitoring : {e}")

# ── Boucle Principale ──────────────────────────────────────────────────────

async def main():
    global main_loop
    print("="*60)
    print(" PHOEBUS CORE - DEMARRAGE (MODULARISÉ)".center(60))
    print("="*60)

    main_loop = asyncio.get_running_loop()
    # Threads annexes
    # On masque les erreurs SDL/AUHAL polluantes sur macOS au boot
    devnull = open(os.devnull, 'w')
    old_stderr = os.dup(sys.stderr.fileno())
    try:
        os.dup2(devnull.fileno(), sys.stderr.fileno())
        threading.Thread(target=run_mobile_server, daemon=True).start()
        threading.Thread(target=listen_and_process, args=(main_loop,), daemon=True).start()
    finally:
        os.dup2(old_stderr, sys.stderr.fileno())
        devnull.close()

    asyncio.create_task(run_telegram_bot(main_loop))
    # threading.Thread(target=monitor_claps, daemon=True).start()

    from PHOEBUS.utils import launch_app, get_lan_ip
    lan_ip = get_lan_ip()
    print(f"[RESEAU] IP LAN : {lan_ip}")
    if PHOEBUS_WS_TOKEN and PHOEBUS_WS_TOKEN != "CHANGE_ME":
        print(f"[RESEAU] Satellite : http://{lan_ip}:8080/?token={PHOEBUS_WS_TOKEN}")

    from PHOEBUS.brain_router import router_status
    brain = router_status()
    print(
        f"[BRAIN] Mode {brain['mode']} | disponibles: "
        f"{', '.join(brain['available']) or 'aucun'} | ordre: "
        f"{', '.join(brain['order'])}"
    )

    from PHOEBUS.automation import demarrer_moteur_automatisation
    demarrer_moteur_automatisation()

    # Pré-chauffage du cache TTS : on synthétise les 30 phrases les plus
    # fréquentes en arrière-plan pour qu'elles soient "instantanées" dès
    # la première utilisation. N'attend pas la fin pour démarrer le reste.
    async def _warmup_tts():
        try:
            from PHOEBUS.response_cache import prewarm
            from PHOEBUS.tts_backends import synthesize_to_file, EDGE_VOICE
            await prewarm(synthesize_to_file, EDGE_VOICE, "auto")
        except Exception as e:
            print(f"[CACHE-TTS] warmup a échoué : {e}")
    asyncio.create_task(_warmup_tts())

    # Pré-chauffage Home Assistant : peuple le cache d'entités pour que le
    # premier prompt système contienne déjà la liste fraîche.
    async def _warmup_ha():
        try:
            from PHOEBUS.home import prewarm_ha_context
            await asyncio.to_thread(prewarm_ha_context)
        except Exception as e:
            print(f"[HA] prewarm échoué : {e}")
    asyncio.create_task(_warmup_ha())

    # ── Wake Word ─────────────────────────────────────────────
    if PHOEBUS_WAKE_ENABLED and _WAKE_WORD_AVAILABLE:
        def _on_wake_word():
            """Appelée par le thread wake word quand 'Hey PHOEBUS' est détecté."""
            if state.is_in_conversation():
                return  # Déjà en mode conversation, inutile de réactiver
            state.extend_conversation(seconds=30)
            asyncio.run_coroutine_threadsafe(
                parler("Oui, je vous écoute.", keep_conversation=False),
                main_loop
            )
        _wake_word_module.start(_on_wake_word)
        print("[WAKE] Détection wake word démarrée.")
    elif PHOEBUS_WAKE_ENABLED:
        print("[WAKE] Module wake_word non disponible, détection désactivée.")
    else:
        print("[WAKE] Détection séparée désactivée (micro réservé au STT principal).")
    # ──────────────────────────────────────────────────────────

    # Moteur de proactivité (silence, rappels, etc.) — tâche asyncio légère.
    asyncio.create_task(proactive.loop(parler))
    asyncio.create_task(system_self_healing())

    # Salutation initiale non bloquante : le WebSocket doit démarrer même si
    # CoreAudio ou le TTS met du temps à rendre la main.
    asyncio.create_task(
        _parler_safe(
            "Bonjour Floriace. Tous les systèmes sont opérationnels.",
            keep_conversation=False,
        )
    )

    print("\n[INIT] Démarrage du serveur WebSocket...")
    # On notifie l'interface qu'elle doit se synchroniser (reload) au cas où c'est un redémarrage
    asyncio.create_task(state.broadcast({"action": "reload_ui"}))
    
    await asyncio.gather(
        start_websocket_server(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[PHOEBUS] Arrêt demandé. Au revoir Floriace.")
