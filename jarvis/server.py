# jarvis/server.py
"""Serveur WebSocket, HTTP mobile et boucle principale de JARVIS."""
import json
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
from jarvis.ai import demander_ia, demander_ia_vision
from jarvis.actions import traiter_reponse_ia
from jarvis.voice import parler, monitor_claps


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
                action = data.get("action")
                
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
                    
                elif action == "stop_parler":
                    state.STOP_PARLER = True
                    
                elif action == "demander_ia":
                    question = data.get("text", "")
                    if question:
                        rep = await demander_ia(question)
                        if not await traiter_reponse_ia(rep):
                            await parler(rep)
                            
                elif action == "demander_ia_vision":
                    question = data.get("text", "")
                    img_b64 = data.get("image", "")
                    if question and img_b64:
                        rep = await demander_ia_vision(question, img_b64)
                        if not await traiter_reponse_ia(rep):
                            await parler(rep)
                            
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

def listen_and_process():
    if not sr:
        print("[MIC] speech_recognition non installe.")
        return
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=1)
            print("[MIC] Prêt à écouter localement...")
            while True:
                if state.is_speaking or state.is_thinking:
                    time.sleep(0.5)
                    continue
                try:
                    state.is_listening = True
                    asyncio.run(state.send_web_state("listening"))
                    audio = r.listen(source, timeout=5, phrase_time_limit=10)
                    
                    if state.is_speaking or state.is_thinking:
                        state.is_listening = False
                        asyncio.run(state.send_web_state("idle"))
                        continue

                    state.is_listening = False
                    asyncio.run(state.send_web_state("thinking"))
                    
                    texte = r.recognize_google(audio, language="fr-FR")
                    print(f"\n[VOUS] {texte}")
                    
                    if "jarvis" in texte.lower():
                        if "mode iron man" in texte.lower() and "active" in texte.lower():
                            state.MODE_IRON_MAN = True
                            asyncio.run(parler("Mode Iron Man activé."))
                            continue
                            
                        rep = asyncio.run(demander_ia(texte))
                        if not asyncio.run(traiter_reponse_ia(rep)):
                            asyncio.run(parler(rep))
                            
                except sr.WaitTimeoutError:
                    state.is_listening = False
                    asyncio.run(state.send_web_state("idle"))
                except sr.UnknownValueError:
                    state.is_listening = False
                    asyncio.run(state.send_web_state("idle"))
                except Exception as e:
                    print(f"[MIC] Erreur de reconnaissance : {e}")
                    state.is_listening = False
                    asyncio.run(state.send_web_state("idle"))
                    time.sleep(2)
    except Exception as e:
        print(f"[MIC] Impossible d'ouvrir le micro : {e}")


# ── Boucle Principale ──────────────────────────────────────────────────────

async def main():
    print("="*60)
    print(" JARVIS CORE - DEMARRAGE (MODULARISÉ)".center(60))
    print("="*60)

    # Threads annexes
    threading.Thread(target=run_mobile_server, daemon=True).start()
    threading.Thread(target=listen_and_process, daemon=True).start()
    threading.Thread(target=monitor_claps, daemon=True).start()

    from jarvis.utils import launch_app, get_lan_ip
    lan_ip = get_lan_ip()
    print(f"[RESEAU] IP LAN : {lan_ip}")
    if JARVIS_WS_TOKEN and JARVIS_WS_TOKEN != "CHANGE_ME":
        print(f"[RESEAU] Satellite : http://{lan_ip}:8080/?token={JARVIS_WS_TOKEN}")

    from jarvis.automation import demarrer_moteur_automatisation
    demarrer_moteur_automatisation()

    print("\n[INIT] Démarrage du serveur WebSocket...")
    await asyncio.gather(
        start_websocket_server(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[JARVIS] Arrêt demandé. Au revoir Floriace.")
