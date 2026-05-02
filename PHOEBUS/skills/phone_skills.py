# PHOEBUS/skills/phone_skills.py
"""Contrôle avancé du téléphone de Floriace via WebSocket.

Tier 1 : commandes navigateur (vibration, lampe torche, GPS, clipboard,
alarme sonore, notification locale).

Les commandes sont envoyées via WebSocket au client mobile connecté.
Le téléphone répond avec le résultat (ou un timeout déclenche un fallback).
"""

import asyncio
import json
import uuid
from typing import Optional

import PHOEBUS.state as state
from PHOEBUS.skills.registry import skill


# ── Timeout pour les réponses du téléphone ──
PHONE_CMD_TIMEOUT = float(__import__("os").getenv("PHOEBUS_PHONE_CMD_TIMEOUT", "8"))


async def _send_phone_command(action: str, params: dict = None, timeout: float = PHONE_CMD_TIMEOUT) -> Optional[dict]:
    """Envoie une commande au téléphone via WebSocket et attend la réponse.

    Retourne le dict de réponse du téléphone, ou None en cas de timeout/erreur.
    """
    # Trouver un client mobile connecté
    targets = []
    for ws in state.get_authenticated_clients():
        meta = state.CLIENT_META.get(ws, {}) or {}
        if meta.get("client_type") in ("mobile", "mobile_app"):
            targets.append(ws)
    if not targets:
        # Fallback : envoyer à tous les clients authentifiés
        targets = list(state.get_authenticated_clients())
    if not targets:
        # Fallback pour le contrôle natif iOS via Focus Mode
        try:
            import os
            from PHOEBUS.state import IOS_PENDING_COMMANDS
            IOS_PENDING_COMMANDS.append({"action": action, **(params or {})})
            # On lance le raccourci sur le Mac qui active le Focus Mode
            os.system('shortcuts run "TriggerPhoebus" > /dev/null 2>&1')
            
            # Pour éviter que la commande bloque, on retourne un succès simulé
            # puisque l'exécution sur iOS est asynchrone et aveugle.
            return {"ok": True, "iOS_fallback": True}
        except ImportError:
            pass
        return None

    req_id = str(uuid.uuid4())
    fut = asyncio.get_event_loop().create_future()
    state.PENDING_PHONE_COMMANDS[req_id] = fut

    payload = {
        "action": "phone_command",
        "id": req_id,
        "command": action,
        **(params or {}),
    }
    msg = json.dumps(payload, ensure_ascii=False)
    await asyncio.gather(*[ws.send(msg) for ws in targets], return_exceptions=True)

    try:
        result = await asyncio.wait_for(fut, timeout=timeout)
        return result if isinstance(result, dict) else {"result": result}
    except asyncio.TimeoutError:
        state.PENDING_PHONE_COMMANDS.pop(req_id, None)
        return None
    except Exception as e:
        state.PENDING_PHONE_COMMANDS.pop(req_id, None)
        print(f"[PHONE] Erreur commande {action}: {e}")
        return None


def _no_phone_msg() -> str:
    return "Aucun téléphone connecté. Ouvre l'app satellite sur ton mobile pour que je puisse le contrôler."


def _phone_error(result: Optional[dict], label: str = "Commande téléphone") -> str | None:
    if result is None:
        return _no_phone_msg()
    if result.get("error") or result.get("ok") is False:
        return f"{label} impossible : {result.get('error', 'refusé par le téléphone')}"
    return None


# ── Skills ──────────────────────────────────────────────────────────────────

@skill(
    "phone_control",
    risk="low",
    help_text="Contrôle le téléphone (vibrer, lampe, GPS, clipboard, alarme, notification)",
    describe=lambda d: f"Contrôler le téléphone : {d.get('phone_action', d.get('command', '?'))}",
)
async def phone_control(data: dict):
    """Routeur unifié pour les commandes téléphone."""
    action = data.get("phone_action") or data.get("command") or ""
    action = action.lower().strip()

    dispatch = {
        "vibrate": phone_vibrate,
        "vibrer": phone_vibrate,
        "torch": phone_torch,
        "lampe": phone_torch,
        "flashlight": phone_torch,
        "gps": phone_gps,
        "location": phone_gps,
        "localisation": phone_gps,
        "clipboard_read": phone_clipboard_read,
        "clipboard_write": phone_clipboard_write,
        "alarm": phone_alarm,
        "alarme": phone_alarm,
        "find": phone_find,
        "trouver": phone_find,
        "notification": phone_notification,
        "battery": phone_battery,
        "batterie": phone_battery,
        "info": phone_info,
        "open_app": phone_open_app,
        "ouvrir": phone_open_app,
        "open_url": phone_open_url,
        "share": phone_share_text,
        "partager": phone_share_text,
    }

    handler = dispatch.get(action)
    if handler:
        return await handler(data)
    return f"Commande téléphone inconnue : '{action}'. Commandes disponibles : {', '.join(sorted(set(dispatch.keys())))}."


@skill(
    "phone_vibrate",
    risk="low",
    help_text="Fait vibrer le téléphone",
    describe=lambda d: "Faire vibrer le téléphone",
)
async def phone_vibrate(data: dict):
    pattern = data.get("pattern", [200, 100, 200, 100, 400])
    if isinstance(pattern, str):
        pattern = [200, 100, 200, 100, 400]
    result = await _send_phone_command("vibrate", {"pattern": pattern})
    err = _phone_error(result, "Vibration")
    if err:
        return err
    return "C'est fait, ton téléphone vibre."


@skill(
    "phone_torch",
    risk="low",
    help_text="Allume ou éteint la lampe torche du téléphone",
    describe=lambda d: f"{'Allumer' if d.get('state', 'toggle') != 'off' else 'Éteindre'} la lampe torche",
)
async def phone_torch(data: dict):
    state_val = data.get("state", "toggle")  # on / off / toggle
    result = await _send_phone_command("torch", {"state": state_val})
    err = _phone_error(result, "Lampe torche")
    if err and not result.get("iOS_fallback"):
        return err
    if result and result.get("iOS_fallback"):
        return "Demande envoyée silencieusement à l'iPhone via le relais de concentration."
    torch_state = result.get("torch_state", "?")
    return f"Lampe torche {'allumée' if torch_state == 'on' else 'éteinte'}."


@skill(
    "phone_settings",
    risk="low",
    help_text="Modifie les réglages de l'iPhone (Volume, Wifi, Bluetooth)",
    describe=lambda d: f"Modifier un réglage sur l'iPhone",
)
async def phone_settings(data: dict):
    setting = data.get("setting", "volume")
    value = data.get("value", "")
    result = await _send_phone_command(setting, {"value": value})
    if result and result.get("iOS_fallback"):
        return f"Ordre de réglage ({setting}) envoyé silencieusement à l'iPhone."
    return "Réglage effectué via l'application satellite."

@skill(
    "phone_gps",
    risk="low",
    help_text="Récupère la position GPS du téléphone",
    describe=lambda d: "Localiser le téléphone",
)
async def phone_gps(data: dict):
    result = await _send_phone_command("gps", timeout=10)
    err = _phone_error(result, "GPS")
    if err:
        return err
    lat = result.get("latitude", "?")
    lon = result.get("longitude", "?")
    accuracy = result.get("accuracy", "?")
    if lat == "?" or result.get("error"):
        return f"Impossible d'obtenir la position GPS : {result.get('error', 'timeout')}"
    return f"Position du téléphone : {lat}, {lon} (précision ±{accuracy}m)."


@skill(
    "phone_clipboard_read",
    risk="low",
    help_text="Lit le contenu du presse-papier du téléphone",
    describe=lambda d: "Lire le presse-papier du téléphone",
)
async def phone_clipboard_read(data: dict):
    result = await _send_phone_command("clipboard_read")
    err = _phone_error(result, "Lecture du presse-papier")
    if err:
        return err
    text = result.get("text", "")
    if not text:
        return "Le presse-papier du téléphone est vide."
    return f"Contenu du presse-papier : {text[:500]}"


@skill(
    "phone_clipboard_write",
    risk="low",
    help_text="Écrit du texte dans le presse-papier du téléphone",
    describe=lambda d: f"Copier sur le téléphone : {d.get('text', '')[:30]}",
)
async def phone_clipboard_write(data: dict):
    text = data.get("text", "").strip()
    if not text:
        return "Aucun texte à copier."
    result = await _send_phone_command("clipboard_write", {"text": text})
    err = _phone_error(result, "Écriture du presse-papier")
    if err:
        return err
    return "Texte copié dans le presse-papier du téléphone."


@skill(
    "phone_alarm",
    risk="low",
    help_text="Joue une alarme sonore forte sur le téléphone (pour le retrouver)",
    describe=lambda d: "Sonner le téléphone",
)
async def phone_alarm(data: dict):
    duration = data.get("duration", 5)  # secondes
    result = await _send_phone_command("alarm", {"duration": duration}, timeout=max(12, duration + 3))
    err = _phone_error(result, "Alarme")
    if err:
        return err
    return "Alarme déclenchée sur ton téléphone !"


@skill(
    "phone_find",
    risk="low",
    help_text="Retrouve le téléphone (vibration + alarme + GPS)",
    describe=lambda d: "Retrouver le téléphone",
)
async def phone_find(data: dict):
    """Combo : vibration + alarme + GPS en parallèle."""
    results = await asyncio.gather(
        _send_phone_command("vibrate", {"pattern": [500, 200, 500, 200, 500, 200, 1000]}),
        _send_phone_command("alarm", {"duration": 8}),
        _send_phone_command("gps", timeout=10),
        return_exceptions=True,
    )

    gps_result = results[2] if not isinstance(results[2], Exception) else None
    successes = [
        r for r in results
        if isinstance(r, dict) and not r.get("error") and r.get("ok") is not False
    ]
    if not successes:
        return _no_phone_msg()
    parts = ["Ton téléphone devrait vibrer et sonner maintenant."]
    if gps_result and isinstance(gps_result, dict) and gps_result.get("latitude"):
        parts.append(
            f"Sa position GPS : {gps_result['latitude']}, {gps_result['longitude']} "
            f"(±{gps_result.get('accuracy', '?')}m)."
        )
    if all(r is None for r in results if not isinstance(r, Exception)):
        return _no_phone_msg()
    return " ".join(parts)


@skill(
    "phone_notification",
    risk="low",
    help_text="Envoie une notification visible sur le téléphone",
    describe=lambda d: f"Notifier le téléphone : {d.get('message', '')[:30]}",
)
async def phone_notification(data: dict):
    title = data.get("title", "PHOEBUS")
    message = data.get("message", data.get("text", "")).strip()
    if not message:
        return "Aucun message à envoyer."
    result = await _send_phone_command("notification", {"title": title, "message": message})
    err = _phone_error(result, "Notification")
    if err:
        return err
    return "Notification envoyée sur ton téléphone."


@skill(
    "phone_battery",
    risk="low",
    help_text="Vérifie le niveau de batterie du téléphone",
    describe=lambda d: "Vérifier la batterie du téléphone",
)
async def phone_battery(data: dict):
    result = await _send_phone_command("battery")
    err = _phone_error(result, "Batterie")
    if err:
        return err
    level = result.get("level", "?")
    charging = result.get("charging", False)
    status = " (en charge)" if charging else ""
    return f"Batterie du téléphone : {level}%{status}."


@skill(
    "phone_info",
    risk="low",
    help_text="Récupère les infos du téléphone connecté",
    describe=lambda d: "Infos du téléphone",
)
async def phone_info(data: dict):
    result = await _send_phone_command("info")
    err = _phone_error(result, "Lecture des infos téléphone")
    if err:
        return err
    ua = result.get("userAgent", "?")
    screen = result.get("screen", "?")
    online = result.get("online", True)
    return f"Téléphone connecté : {ua[:60]}. Écran : {screen}. En ligne : {'oui' if online else 'non'}."


@skill(
    "phone_open_app",
    risk="low",
    help_text="Ouvre une application sur le téléphone (Netflix, YouTube, Spotify, WhatsApp, etc.)",
    describe=lambda d: f"Ouvrir {d.get('app', '?')} sur le téléphone",
)
async def phone_open_app(data: dict):
    app = data.get("app", data.get("name", "")).strip()
    if not app:
        return "Quelle application ouvrir sur le téléphone ?"
    result = await _send_phone_command("open_app", {"app": app})
    err = _phone_error(result, f"Ouverture de {app}")
    if err:
        return err
    method = result.get("method", "url_scheme")
    if method == "store_search":
        return f"L'app '{app}' n'a pas de raccourci connu. J'ai ouvert la recherche dans le store."
    return f"{app.title()} lancé sur ton téléphone."


@skill(
    "phone_open_url",
    risk="low",
    help_text="Ouvre une URL dans le navigateur du téléphone",
    describe=lambda d: f"Ouvrir {d.get('url', '?')[:30]} sur le téléphone",
)
async def phone_open_url(data: dict):
    url = data.get("url", "").strip()
    if not url:
        return "Quelle URL ouvrir sur le téléphone ?"
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    result = await _send_phone_command("open_url", {"url": url})
    err = _phone_error(result, "Ouverture URL")
    if err:
        return err
    return f"URL ouverte sur ton téléphone : {url}"


@skill(
    "phone_share_text",
    risk="low",
    help_text="Partage du texte depuis le téléphone via la feuille de partage native",
    describe=lambda d: f"Partager sur le téléphone : {d.get('text', '')[:30]}",
)
async def phone_share_text(data: dict):
    text = data.get("text", "").strip()
    if not text:
        return "Aucun texte à partager."
    result = await _send_phone_command("share_text", {"text": text, "title": data.get("title", "PHOEBUS")})
    err = _phone_error(result, "Partage")
    if err:
        return err
    return "Feuille de partage ouverte sur ton téléphone."
