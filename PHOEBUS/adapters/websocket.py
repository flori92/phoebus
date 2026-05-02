"""Adaptateur WebSocket PHOEBUS."""

from __future__ import annotations

import json

import PHOEBUS.state as state
from PHOEBUS.ai import demander_ia_vision
from PHOEBUS.config import WS_AUTH_REQUIRED, websockets
from PHOEBUS.desktop import executer_action_pc
from PHOEBUS.router import executer_commande_generique, traiter_reponse_ia
from PHOEBUS.security import audit_log, sanitize_action_data
from PHOEBUS.voice import parler
from PHOEBUS.ws_pairing import (
    PAIRING_ENABLED,
    enroll_pairing,
    mark_seen,
    validate_pairing,
)


def _payload_text(data: dict, *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _client_ip(websocket) -> str:
    if websocket.remote_address:
        return websocket.remote_address[0]
    return "unknown"


def _is_interface_client(client_type: str) -> bool:
    return client_type in {"web", "web_dashboard", "mobile", "mobile_app", "unknown"}


async def _handle_auth(websocket, data: dict, client_ip: str) -> bool:
    client_type = data.get("client_type", "unknown")
    client_name = data.get("client_name", "")
    pair_device_id = data.get("pair_device_id")
    pair_secret = data.get("pair_secret")

    pairing_payload = {}
    if PAIRING_ENABLED:
        if pair_device_id and pair_secret and validate_pairing(pair_device_id, pair_secret):
            mark_seen(pair_device_id, client_ip)
        else:
            enrolled = enroll_pairing(
                client_ip=client_ip,
                client_type=client_type,
                client_name=client_name,
            )
            if not enrolled:
                await state.send_ws_json(
                    websocket,
                    {
                        "action": "auth_failed",
                        "reason": "pairing_required",
                        "message": "Pairing local requis.",
                    },
                )
                audit_log("ws_pairing_rejected", ip=client_ip, client_type=client_type)
                return False
            pair_device_id = enrolled["device_id"]
            pairing_payload = {
                "pair_device_id": enrolled["device_id"],
                "pair_secret": enrolled["secret"],
            }
            audit_log("ws_pairing_enrolled", ip=client_ip, client_type=client_type)

    state.register_authenticated_client(
        websocket,
        {
            **data,
            "client_type": client_type,
            "pair_device_id": pair_device_id or "",
        },
    )
    await state.send_ws_json(websocket, {"action": "auth_ok", **pairing_payload})
    audit_log("ws_client_identified", ip=client_ip, client_type=client_type)
    if _is_interface_client(client_type) and not state.interface_deja_connectee:
        await parler("Interface connectée.", keep_conversation=False)
        state.interface_deja_connectee = True
    return True


async def ws_handler(websocket):
    if not websockets:
        return

    state.CONNECTED_CLIENTS.add(websocket)
    client_ip = _client_ip(websocket)
    print(f"[WEB] Nouvelle connexion WebSocket depuis {client_ip}")

    if PAIRING_ENABLED or WS_AUTH_REQUIRED:
        await state.send_ws_json(websocket, {"action": "auth_required", "pairing": PAIRING_ENABLED})
    else:
        state.register_authenticated_client(
            websocket, {"client_type": "unknown", "client_name": "auto-auth"}
        )
        await state.send_ws_json(websocket, {"action": "auth_ok"})
        if not state.interface_deja_connectee:
            await parler("Interface connectée.", keep_conversation=False)
            state.interface_deja_connectee = True

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get("action") or data.get("type")

                if action == "auth":
                    await _handle_auth(websocket, data, client_ip)
                    continue

                if websocket not in state.AUTHENTICATED_CLIENTS:
                    await state.send_ws_json(
                        websocket, {"action": "auth_required", "pairing": PAIRING_ENABLED}
                    )
                    continue

                safe_data = sanitize_action_data(data)
                if action not in {"audio_chunk", "screen_capture_result", "pong", "audio_level"}:
                    audit_log("ws_command_received", ip=client_ip, **safe_data)

                if action == "ping":
                    await state.send_ws_json(websocket, {"action": "pong"})

                elif action == "test_vocal":
                    await parler("Test vocal depuis l'interface web.")

                elif action == "PHOEBUS_parler":
                    txt = _payload_text(data, "text", "message", "command", "commande", "query")
                    if txt:
                        await parler(txt)

                elif action == "stop_parler" or action == "stop_audio":
                    state.STOP_PARLER = True

                elif action == "demander_ia" or action == "mobile_command":
                    question = _payload_text(
                        data, "text", "message", "command", "commande", "query", "question"
                    )
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
                    if res:
                        await parler(res)

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
                    req_id = data.get("id")
                    img_b64 = data.get("image")
                    if req_id in state.PENDING_PHONE_CAPTURES:
                        fut = state.PENDING_PHONE_CAPTURES.pop(req_id)
                        if not fut.done():
                            fut.set_result(img_b64)

                elif action == "phone_command_result":
                    req_id = data.get("id")
                    if req_id in state.PENDING_PHONE_COMMANDS:
                        fut = state.PENDING_PHONE_COMMANDS.pop(req_id)
                        if not fut.done():
                            fut.set_result(data)

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
        if _is_interface_client(meta.get("client_type", "")) and state.interface_deja_connectee:
            if not any(_is_interface_client(m.get("client_type", "")) for m in state.CLIENT_META.values()):
                state.interface_deja_connectee = False
                print("[WEB] Interface deconnectee.")
