"""Contrôle direct d'objets connectés via MQTT.

Beaucoup de devices DIY (ESP32, Tasmota, Shelly, Zigbee2MQTT, IKEA, etc.)
parlent MQTT nativement. Plutôt que de tout passer par Home Assistant,
PHOEBUS peut publier/écouter directement sur le broker.

Configuration (.env) :
    MQTT_HOST=192.168.1.10
    MQTT_PORT=1883
    MQTT_USERNAME=phoebus    (optionnel)
    MQTT_PASSWORD=...        (optionnel)
    MQTT_TLS=0               (1 pour TLS sur 8883)
    MQTT_CLIENT_ID=phoebus

Actions exposées via le dispatcher :
- mqtt_publish : publier une valeur sur un topic
- mqtt_subscribe : s'abonner et lire les N dernières valeurs
- mqtt_discover : liste les topics actifs (sniff 10 s sur #)

Dépendance optionnelle : `pip install paho-mqtt`. Si absent, les
fonctions renvoient un message clair et n'explosent pas.
"""
import os
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Optional


MQTT_HOST = os.getenv("MQTT_HOST", "").strip()
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "").strip()
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "").strip()
MQTT_TLS = os.getenv("MQTT_TLS", "0").strip().lower() in ("1", "true", "yes", "on")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "phoebus").strip()


# Cache du dernier payload reçu par topic, pour répondre vite à mqtt_subscribe.
_last_values: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
_topics_seen: Dict[str, dict] = {}
_client = None
_client_lock = threading.Lock()


def _try_paho():
    try:
        import paho.mqtt.client as mqtt
        return mqtt
    except Exception:
        return None


def _ensure_client():
    """Crée et démarre le client MQTT global (singleton, thread)."""
    global _client
    with _client_lock:
        if _client is not None:
            return _client
        if not MQTT_HOST:
            return None
        mqtt = _try_paho()
        if mqtt is None:
            print("[MQTT] paho-mqtt non installé. `pip install paho-mqtt`.")
            return None
        try:
            cl = mqtt.Client(client_id=MQTT_CLIENT_ID, clean_session=True)
            if MQTT_USERNAME:
                cl.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
            if MQTT_TLS:
                cl.tls_set()

            def _on_message(client, userdata, msg):
                try:
                    payload = msg.payload.decode("utf-8", errors="replace")
                except Exception:
                    payload = repr(msg.payload)
                _last_values[msg.topic].append({"ts": time.time(), "value": payload})
                _topics_seen[msg.topic] = {
                    "last_seen": time.time(),
                    "last_value": payload,
                }

            cl.on_message = _on_message
            cl.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            cl.loop_start()
            _client = cl
            print(f"[MQTT] Connecté à {MQTT_HOST}:{MQTT_PORT}")
            return _client
        except Exception as e:
            print(f"[MQTT] Connexion KO : {e}")
            return None


def publish(topic: str, payload: str, qos: int = 0, retain: bool = False) -> str:
    """Publie sur un topic. Renvoie un message de statut humain."""
    if not topic:
        return "Topic MQTT vide."
    cl = _ensure_client()
    if cl is None:
        return "MQTT n'est pas configuré (vérifie MQTT_HOST et pip install paho-mqtt)."
    try:
        result = cl.publish(topic, payload, qos=qos, retain=retain)
        result.wait_for_publish(timeout=2.0)
        if result.rc == 0:
            return f"Publié sur {topic}."
        return f"Échec publication sur {topic} (rc={result.rc})."
    except Exception as e:
        return f"Erreur MQTT publish : {e}"


def subscribe(topic: str, wait_s: float = 5.0) -> str:
    """S'abonne et renvoie le dernier payload reçu (ou attend `wait_s`).

    Si l'abonnement existe déjà depuis un appel précédent, renvoie tout de
    suite la dernière valeur connue.
    """
    if not topic:
        return "Topic MQTT vide."
    cl = _ensure_client()
    if cl is None:
        return "MQTT n'est pas configuré."
    try:
        cl.subscribe(topic)
    except Exception as e:
        return f"Subscribe KO : {e}"

    # Cas 1 : on a déjà une valeur en cache.
    if _last_values.get(topic):
        latest = _last_values[topic][-1]
        return f"{topic} = {latest['value']}"

    # Cas 2 : on attend.
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if _last_values.get(topic):
            latest = _last_values[topic][-1]
            return f"{topic} = {latest['value']}"
        time.sleep(0.15)

    return f"Pas de message reçu sur {topic} en {wait_s:.1f} s."


def discover(wait_s: float = 10.0, max_topics: int = 60) -> str:
    """Sniffe le broker (#) pour révéler les devices/topics actifs."""
    cl = _ensure_client()
    if cl is None:
        return "MQTT n'est pas configuré."
    try:
        cl.subscribe("#")
    except Exception as e:
        return f"Subscribe wildcard KO : {e}"
    time.sleep(wait_s)
    if not _topics_seen:
        return "Aucun topic actif détecté."
    items = sorted(
        _topics_seen.items(), key=lambda kv: kv[1]["last_seen"], reverse=True
    )[:max_topics]
    lignes = []
    for topic, meta in items:
        val = (meta.get("last_value") or "").strip()
        if len(val) > 60:
            val = val[:57] + "..."
        lignes.append(f"  {topic} = {val}")
    return f"{len(_topics_seen)} topics actifs (top {len(items)}) :\n" + "\n".join(lignes)


def status() -> str:
    """Statut court pour debug : "MQTT broker.local (12 topics observés)"."""
    if not MQTT_HOST:
        return "MQTT non configuré."
    cl = _ensure_client()
    if cl is None:
        return f"MQTT configuré ({MQTT_HOST}:{MQTT_PORT}) mais pas connecté."
    return f"MQTT connecté à {MQTT_HOST}:{MQTT_PORT} ({len(_topics_seen)} topics observés)."
