# jarvis/server.py
"""Serveur WebSocket, HTTP mobile et boucle principale de JARVIS."""
import json
import time
import asyncio
import threading
import http.server
import socketserver
import hmac
import hashlib

from jarvis.config import (
    websockets, sr, DEFAULT_WS_PORT, DEFAULT_MOBILE_PORT, MOBILE_DIR,
    JARVIS_WS_TOKEN, WS_AUTH_REQUIRED
)
import jarvis.state as state
from jarvis.security import audit_log, sanitize_action_data
from jarvis.desktop import executer_action_pc
from jarvis.ai import demander_ia, demander_ia_vision, demander_ia_stream
from jarvis.actions import traiter_reponse_ia
from jarvis.voice import parler, monitor_claps
from jarvis.stt_backends import get_backend as get_stt_backend
from jarvis.clarify import transcription_incertaine
from jarvis import proactive

# Imports optionnels des nouveaux modules
try:
    from jarvis import wake_word as _wake_word_module
    _WAKE_WORD_AVAILABLE = True
except ImportError:
    _WAKE_WORD_AVAILABLE = False

try:
    from jarvis.multi_user import identifier_speaker, MULTI_USER_ENABLED
except ImportError:
    identifier_speaker = None
    MULTI_USER_ENABLED = False

try:
    from jarvis.memory_timeline import enregistrer_evenement as _timeline_evt
except ImportError:
    _timeline_evt = None


# ── Sécurité WebSocket ─────────────────────────────────────────────────────

def verify_token(provided_token):
    if not JARVIS_WS_TOKEN or JARVIS_WS_TOKEN in {"CHANGE_ME", "VOTRE_TOKEN_ICI"}:
        return True
    if not provided_token:
        return False
    try:
        return hmac.compare_digest(
            hashlib.sha256(provided_token.encode()).digest(),
            hashlib.sha256(JARVIS_WS_TOKEN.encode()).digest()
        )
    except Exception:
        return False


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
            await parler("Interface connectée.")
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
                            await parler("Interface web authentifiée.")
                            state.interface_deja_connectee = True
                        elif client_type == "mobile_app":
                            await parler("Satellite mobile authentifié.")
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
                    
                elif action == "jarvis_parler":
                    txt = data.get("text", "")
                    if txt: await parler(txt)
                    
                elif action == "stop_parler" or action == "stop_audio":
                    state.STOP_PARLER = True
                    
                elif action == "demander_ia" or action == "mobile_command":
                    question = data.get("text", "")
                    if question:
                        state.extend_conversation()
                        state.mark_user_activity()

                        # Streaming : on parle phrase par phrase dès que le LLM
                        # produit. Si la réponse est une commande JSON, on
                        # supprime le streaming voix et on traite à la fin.
                        spoken = {"v": False}

                        async def _on_sentence(s):
                            spoken["v"] = True
                            await parler(s)

                        rep = await demander_ia_stream(question, on_sentence=_on_sentence)

                        if "{" in (rep or "") and "}" in (rep or ""):
                            await traiter_reponse_ia(rep)
                        elif not spoken["v"] and rep:
                            # Aucune phrase n'a été streamée (ex: fast-path texte) :
                            # on gère comme avant.
                            if not await traiter_reponse_ia(rep):
                                await parler(rep)
                        state.extend_conversation()

                elif action == "demander_ia_vision":
                    question = data.get("text", "")
                    img_b64 = data.get("image", "")
                    if question and img_b64:
                        state.extend_conversation()
                        state.mark_user_activity()
                        rep = await demander_ia_vision(question, img_b64)
                        if not await traiter_reponse_ia(rep):
                            await parler(rep)
                        state.extend_conversation()
                            
                elif action == "action_pc":
                    cmd = data.get("commande", "")
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
    try:
        from jarvis.utils import find_available_port
        port = find_available_port(DEFAULT_WS_PORT)
        print(f"[WEB] Serveur WebSocket sur ws://0.0.0.0:{port}")
        if WS_AUTH_REQUIRED:
            print("[WEB] AUTHENTIFICATION REQUISE (Token actif).")
        async with websockets.serve(ws_handler, "0.0.0.0", port):
            await asyncio.Future()
    except Exception as e:
        print(f"[WEB] Erreur WebSocket : {e}")


# ── Serveur Mobile (HTTP) ──────────────────────────────────────────────────

class MobileHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(MOBILE_DIR), **kwargs)
        
    def log_message(self, format, *args):
        pass
        
    def do_POST(self):
        """Webhooks: Reçoit les événements instantanés de Home Assistant."""
        if self.path == '/webhook/ha_event':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                event = data.get("event", "inconnu")
                message = data.get("message", "")
                print(f"[WEBHOOK] Événement HA reçu : {event}")
                
                # Réaction instantanée de Jarvis
                if message:
                    asyncio.run(parler(message))
                    
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            except Exception as e:
                print(f"[WEBHOOK] Erreur : {e}")
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


def run_mobile_server():
    try:
        from jarvis.utils import find_available_port
        port = find_available_port(DEFAULT_MOBILE_PORT)
        with socketserver.TCPServer(("0.0.0.0", port), MobileHandler) as httpd:
            print(f"[MOBILE] App satellite dispo sur http://0.0.0.0:{port}")
            httpd.serve_forever()
    except Exception as e:
        print(f"[MOBILE] Serveur erreur : {e}")


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
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=1)
            print("[MIC] Prêt à écouter localement...")
            while True:
                # Suppression du bloc 'if state.is_speaking or state.is_thinking: continue'
                # pour permettre l'interruption (Barge-in).
                try:
                    state.is_listening = True
                    asyncio.run_coroutine_threadsafe(state.send_web_state("listening"), main_loop)
                    # On écoute. Le Recognizer de SpeechRecognition gère l'énergie de manière dynamique par défaut.
                    audio = r.listen(source, timeout=10, phrase_time_limit=10)

                    # Si on est en train de parler et qu'une parole est détectée,
                    # on signale au moteur TTS de s'arrêter.
                    if state.is_speaking:
                        print("[MIC] Parole détectée pendant que Jarvis parle. Interruption...")
                        state.STOP_PARLER = True

                    state.is_listening = False
                    asyncio.run_coroutine_threadsafe(state.send_web_state("thinking"), main_loop)
                    try:
                        texte = stt_recognize(audio)
                    except sr.UnknownValueError:
                        raise
                    except Exception as e:
                        print(f"[MIC] STT {stt_name} a échoué : {e}")
                        raise sr.UnknownValueError()

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
                    WAKE_WORDS = ["jarvis", "jarv", " jar", "service", "j'arrive", "charvis", "darvis"]
                    wake = any(w in texte_l for w in WAKE_WORDS)
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
                            if texte_l.startswith(w):
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
                            "stop jarvis", "merci jarvis", "c'est bon jarvis",
                        )
                    ):
                        state.end_conversation()
                        asyncio.run_coroutine_threadsafe(state.send_web_state("idle"), main_loop)
                        continue

                    async def process_ia(q):
                        spoken = {"v": False}

                        async def _on_sentence(s):
                            spoken["v"] = True
                            await parler(s)

                        rep = await demander_ia_stream(q, on_sentence=_on_sentence)

                        if "{" in (rep or "") and "}" in (rep or ""):
                            await traiter_reponse_ia(rep)
                        elif not spoken["v"] and rep:
                            if not await traiter_reponse_ia(rep):
                                await parler(rep)
                        # Après chaque tour, on reste à l'écoute naturellement.
                        state.extend_conversation()

                    state.extend_conversation()
                    asyncio.run_coroutine_threadsafe(process_ia(cleaned_texte), main_loop)
                            
                except sr.WaitTimeoutError:
                    if state.is_in_conversation():
                        print("[MIC] Silence détecté, Jarvis se remet en veille.")
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
        print(f"[MIC] Impossible d'ouvrir le micro : {e}")


# ── Boucle Principale ──────────────────────────────────────────────────────

async def main():
    print("="*60)
    print(" JARVIS CORE - DEMARRAGE (MODULARISÉ)".center(60))
    print("="*60)

    main_loop = asyncio.get_running_loop()
    # Threads annexes
    threading.Thread(target=run_mobile_server, daemon=True).start()
    threading.Thread(target=listen_and_process, args=(main_loop,), daemon=True).start()
    # threading.Thread(target=monitor_claps, daemon=True).start()

    from jarvis.utils import launch_app, get_lan_ip
    lan_ip = get_lan_ip()
    print(f"[RESEAU] IP LAN : {lan_ip}")
    if JARVIS_WS_TOKEN and JARVIS_WS_TOKEN != "CHANGE_ME":
        print(f"[RESEAU] Satellite : http://{lan_ip}:8080/?token={JARVIS_WS_TOKEN}")

    from jarvis.brain_router import router_status
    brain = router_status()
    print(
        f"[BRAIN] Mode {brain['mode']} | disponibles: "
        f"{', '.join(brain['available']) or 'aucun'} | ordre: "
        f"{', '.join(brain['order'])}"
    )

    from jarvis.automation import demarrer_moteur_automatisation
    demarrer_moteur_automatisation()

    # Pré-chauffage du cache TTS : on synthétise les 30 phrases les plus
    # fréquentes en arrière-plan pour qu'elles soient "instantanées" dès
    # la première utilisation. N'attend pas la fin pour démarrer le reste.
    async def _warmup_tts():
        try:
            from jarvis.response_cache import prewarm
            from jarvis.tts_backends import synthesize_to_file, EDGE_VOICE
            await prewarm(synthesize_to_file, EDGE_VOICE, "auto")
        except Exception as e:
            print(f"[CACHE-TTS] warmup a échoué : {e}")
    asyncio.create_task(_warmup_tts())

    # Pré-chauffage Home Assistant : peuple le cache d'entités pour que le
    # premier prompt système contienne déjà la liste fraîche.
    async def _warmup_ha():
        try:
            from jarvis.home import prewarm_ha_context
            await asyncio.to_thread(prewarm_ha_context)
        except Exception as e:
            print(f"[HA] prewarm échoué : {e}")
    asyncio.create_task(_warmup_ha())

    # ── Wake Word ─────────────────────────────────────────────
    if _WAKE_WORD_AVAILABLE:
        def _on_wake_word():
            """Appelée par le thread wake word quand 'Hey Jarvis' est détecté."""
            if state.is_in_conversation():
                return  # Déjà en mode conversation, inutile de réactiver
            state.extend_conversation(seconds=30)
            asyncio.run_coroutine_threadsafe(
                parler("Oui, je vous écoute."),
                main_loop
            )
        _wake_word_module.start(_on_wake_word)
        print("[WAKE] Détection wake word démarrée.")
    else:
        print("[WAKE] Module wake_word non disponible, détection désactivée.")
    # ──────────────────────────────────────────────────────────

    # Moteur de proactivité (silence, rappels, etc.) — tâche asyncio légère.
    asyncio.create_task(proactive.loop(parler))

    # Salutation initiale
    await parler("Bonjour Floriace. Tous les systèmes sont opérationnels.")

    print("\n[INIT] Démarrage du serveur WebSocket...")
    await asyncio.gather(
        start_websocket_server(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[JARVIS] Arrêt demandé. Au revoir Floriace.")
