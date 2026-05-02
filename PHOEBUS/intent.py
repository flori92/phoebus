"""Dispatcher d'intention local — fast-path des commandes évidentes.

Objectif : court-circuiter l'appel LLM pour les commandes simples et répétitives
(allumer/éteindre une pièce, demander l'heure ou la date, ouvrir un dossier
connu, etc.). Latence : ~50 ms au lieu de ~1,2 s round-trip cloud.
"""

import re
import time
import json
from typing import Optional

# ── Normalisation ─────────────────────────────────────────────────────────


def _norm(texte: str) -> str:
    t = (texte or "").lower().strip()
    t = t.rstrip("?.!,;:")
    t = re.sub(r"\s+", " ", t)
    t = t.replace("s'il te plaît", "").replace("s'il te plait", "")
    t = t.replace("s'il vous plaît", "").replace("s'il vous plait", "")
    t = t.replace("stp", "").replace("svp", "").strip()
    return t


# ── Table des pièces reconnues ────────────────────────────────────────────
PIECES_ALIAS = {
    "salon": "salon",
    "sejour": "salon",
    "séjour": "salon",
    "living": "salon",
    "cuisine": "cuisine",
    "chambre": "chambre",
    "bureau": "bureau",
    "couloir": "couloir",
    "entree": "entree",
    "entrée": "entree",
    "salle de bain": "salle_de_bain",
    "sdb": "salle_de_bain",
    "toilettes": "toilettes",
    "wc": "toilettes",
    "garage": "garage",
    "cave": "cave",
    "terrasse": "terrasse",
    "jardin": "jardin",
}

_PIECE_PATTERN = "(?:" + "|".join(sorted(PIECES_ALIAS.keys(), key=len, reverse=True)) + ")"
_WAKE_PREFIX = r"(?:(?:phoebus|phébus|fébus|febus|feubus|rebus)[, ]*)?"


# ── Patterns ──────────────────────────────────────────────────────────────

_RE_ALLUME = re.compile(
    rf"^{_WAKE_PREFIX}(?:allume|éclaire|lumiere|lumière).+?(?P<piece>{_PIECE_PATTERN})$"
)
_RE_ETEINS = re.compile(rf"^{_WAKE_PREFIX}(?:éteins|eteins|coupe).+?(?P<piece>{_PIECE_PATTERN})$")
_RE_HEURE = re.compile(
    rf"^{_WAKE_PREFIX}(?:quelle heure est[- ]il|il est quelle heure|tu as l[' ]heure)$"
)
_RE_DATE = re.compile(
    rf"^{_WAKE_PREFIX}(?:quel jour (?:sommes|on est|est)|quelle (?:est la )?date)$"
)
_RE_THERMOSTAT = re.compile(
    rf"^{_WAKE_PREFIX}(?:mets|règle|regle|passe)\s+(?:le\s+)?thermostat\s+(?:à|a|sur)?\s*(?P<temperature>\d+(?:[,.]\d+)?)"
)
_RE_TIMER = re.compile(
    rf"^{_WAKE_PREFIX}(?:mets|lance|démarre|demarre|programme)?\s*(?:un\s+)?(?:minuteur|timer)\s*(?:de\s+)?(?P<n>\d+)\s*(?P<u>s|sec|seconde|secondes|min|minute|minutes|h|heure|heures)?(?:\s+pour\s+(?P<label>.+))?$"
)
_RE_RAPPEL = re.compile(
    rf"^{_WAKE_PREFIX}rappelle[- ]moi\s+dans\s+(?P<n>\d+)\s*(?P<u>s|sec|seconde|secondes|min|minute|minutes|h|heure|heures)\s+(?:de|d')\s*(?P<label>.+)$"
)
_RE_SYS_STATS = re.compile(
    rf"^{_WAKE_PREFIX}(?:état du système|utilisation cpu|niveau de batterie)$"
)
_RE_SYS_VOLUME = re.compile(
    rf"^{_WAKE_PREFIX}(?:mets|règle|regle)\s+le\s+volume\s+syst[eè]me\s+(?:à|a|sur)?\s*(?P<percent>\d+)"
)
_RE_IP = re.compile(r"\b(?P<ip>(?:\d{1,3}\.){3}\d{1,3})\b")
_RE_MAC = re.compile(r"\b(?P<mac>[0-9a-f]{2}(?::[0-9a-f]{2}){5})\b", re.IGNORECASE)
_RE_EMAIL_ADDRESS = re.compile(r"(?P<email>[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})", re.IGNORECASE)

_RE_WAKE_STRIP = re.compile(r"^(?:phoebus|phébus|fébus|febus|feubus|rebus)[, ]*", re.IGNORECASE)
_RE_METEO_CITY = (
    re.compile(
        r"(?:météo|meteo|temps|prévisions|previsions)(?:\s+(?:pour|à|a|sur|de|d'))\s+(?P<ville>[a-zà-ÿ' -]+)$"
    ),
    re.compile(r"quel temps fait[- ]il(?:\s+(?:à|a|sur))?\s+(?P<ville>[a-zà-ÿ' -]+)$"),
)
_METEO_MARKERS = (
    "météo",
    "meteo",
    "quel temps",
    "le temps",
    "prévision",
    "prevision",
    "prévisions",
    "previsions",
    "il fait quoi",
    "il va pleuvoir",
    "va-t-il pleuvoir",
    "va t il pleuvoir",
)
_METEO_PERIOD_MARKERS = (
    "aujourd",
    "journée",
    "journee",
    "ce matin",
    "cet après-midi",
    "cet apres-midi",
    "ce soir",
    "du jour",
)
_METEO_CITY_STOPWORDS = (
    "aujourd",
    "journée",
    "journee",
    "jour",
    "matin",
    "soir",
    "après-midi",
    "apres-midi",
    "dehors",
    "ici",
    "maintenant",
)
_MEDIA_ACTION_MARKERS = (
    "je veux regarder",
    "j'aimerais regarder",
    "jaimerais regarder",
    "propose",
    "proposes",
    "recommande",
    "recommandes",
    "trouve moi",
    "trouve-moi",
    "mets moi",
    "mets-moi",
    "lance moi",
    "lance-moi",
    "on regarde",
    "envie de regarder",
)
_MEDIA_MARKERS = ("film", "films", "série", "serie", "documentaire", "vod", "streaming")
_MEDIA_GENRES = {
    "comedie": ("comique", "comiques", "drôle", "drole", "marrant", "humour", "comedie", "comédie"),
    "action": ("action", "combat", "explosif"),
    "science-fiction": ("science-fiction", "sci-fi", "sf", "futuriste"),
    "horreur": ("horreur", "peur", "flippant", "épouvante", "epouvante"),
    "thriller": ("thriller", "suspense", "policier"),
    "animation": ("animation", "anime", "dessin animé", "dessin anime"),
    "famille": ("famille", "familial", "en famille"),
    "drame": ("drame", "dramatique"),
}
_MEDIA_PLATFORMS = {
    "netflix": "netflix",
    "prime video": "prime",
    "amazon prime": "prime",
    "prime": "prime",
    "disney+": "disney",
    "disney": "disney",
    "canal+": "canal",
    "canal": "canal",
    "youtube": "youtube",
    "justwatch": "justwatch",
}
_EMAIL_ACTION_MARKERS = (
    "envoie un mail",
    "envoie un email",
    "envoie un e-mail",
    "envoie un message",
    "envoyer un mail",
    "envoyer un email",
    "envoyer un e-mail",
    "envoyer un message",
    "prépare un mail",
    "prepare un mail",
    "prépare un email",
    "prepare un email",
    "prépare un e-mail",
    "prepare un e-mail",
    "prépare un message",
    "prepare un message",
    "écris un mail",
    "ecris un mail",
    "écris un email",
    "ecris un email",
    "écris un message",
    "ecris un message",
)


class IntentResult:
    __slots__ = ("name", "reply", "confidence")

    def __init__(self, name: str, reply: str, confidence: float = 1.0):
        self.name = name
        self.reply = reply
        self.confidence = confidence


def _unite_to_seconds(n: int, unit: str) -> int:
    u = (unit or "min").lower()
    if u.startswith("s"):
        return n
    if u.startswith("h"):
        return n * 3600
    return n * 60


def _detect_meteo(t: str) -> Optional[IntentResult]:
    if not any(marker in t for marker in _METEO_MARKERS):
        return None

    sans_wake = _RE_WAKE_STRIP.sub("", t).strip()
    ville = ""
    for pattern in _RE_METEO_CITY:
        m = pattern.search(sans_wake)
        if not m:
            continue
        candidate = (m.group("ville") or "").strip(" ,")
        candidate = re.sub(r"^(?:la|le|les|l'|de la|du|des)\s+", "", candidate).strip()
        if candidate and not any(candidate.startswith(stop) for stop in _METEO_CITY_STOPWORDS):
            ville = candidate
            break

    payload = {"action": "meteo"}
    if ville:
        payload["ville"] = ville
    if any(marker in sans_wake for marker in _METEO_PERIOD_MARKERS):
        payload["periode"] = "journee"
    return IntentResult("meteo", json.dumps(payload))


def _detect_media(t: str) -> Optional[IntentResult]:
    if not any(marker in t for marker in _MEDIA_MARKERS):
        return None
    if not any(marker in t for marker in _MEDIA_ACTION_MARKERS):
        return None

    kind = "serie" if "série" in t or "serie" in t else "film"
    if "documentaire" in t:
        kind = "documentaire"

    genre = ""
    for genre_name, aliases in _MEDIA_GENRES.items():
        if any(alias in t for alias in aliases):
            genre = genre_name
            break
    if not genre:
        genre = "comedie" if "film" in t else "recommandation"

    platform = "justwatch"
    for marker, value in _MEDIA_PLATFORMS.items():
        if marker in t:
            platform = value
            break

    payload = {
        "action": "media_recommendations",
        "kind": kind,
        "genre": genre,
        "platform": platform,
        "open": True,
    }
    return IntentResult("media_recommendations", json.dumps(payload))


def _clean_email_part(value: str) -> str:
    value = (value or "").strip(" ,.;:!?")
    value = re.sub(r"^(?:le|la|l'|un|une)\s+", "", value).strip()
    return value


def _detect_email(t: str) -> Optional[IntentResult]:
    if not any(marker in t for marker in _EMAIL_ACTION_MARKERS):
        return None

    sans_wake = _RE_WAKE_STRIP.sub("", t).strip()
    match = _RE_EMAIL_ADDRESS.search(sans_wake)
    if not match:
        return None

    recipient = match.group("email")
    tail = sans_wake[match.end():].strip(" ,.;:")
    subject = "Message de PHOEBUS"
    body = ""

    subject_patterns = (
        r"(?:avec\s+)?(?:comme\s+)?(?:le\s+)?sujet\s+(?P<subject>.+?)(?:\s+(?:et|,)\s+(?:le\s+)?(?:texte|message|corps|contenu)\s+|$)",
        r"(?:objet)\s+(?P<subject>.+?)(?:\s+(?:et|,)\s+(?:le\s+)?(?:texte|message|corps|contenu)\s+|$)",
    )
    for pattern in subject_patterns:
        m = re.search(pattern, tail)
        if m:
            subject = _clean_email_part(m.group("subject"))
            break

    body_patterns = (
        r"(?:le\s+)?(?:texte|message|corps|contenu)\s+(?:est\s+)?(?P<body>.+)$",
        r"(?:disant|qui dit)\s+(?P<body>.+)$",
    )
    for pattern in body_patterns:
        m = re.search(pattern, tail)
        if m:
            body = _clean_email_part(m.group("body"))
            break

    if not body:
        before_address = sans_wake[:match.start()].strip()
        fallback = re.sub(
            r"^(?:envoie|envoyer|prépare|prepare|écris|ecris)\s+"
            r"(?:un\s+)?(?:mail|email|e-mail|message)\s+(?:à|a|pour)\s*",
            "",
            before_address,
        ).strip()
        body = _clean_email_part(fallback)

    if not body:
        body = "Ceci est un test."

    payload = {
        "action": "write_email",
        "recipient": recipient,
        "subject": subject or "Message de PHOEBUS",
        "body": body,
    }
    return IntentResult("write_email", json.dumps(payload, ensure_ascii=False))


def _timer_payload(duration_s: int, label: str = "", kind: str = "timer") -> str:
    payload = {
        "action": "timer_set",
        "duration_s": int(duration_s),
        "kind": kind,
        "label": (label or "").strip(),
    }
    return json.dumps(payload, ensure_ascii=False)


def _detect_spotify(t: str) -> Optional[IntentResult]:
    if t in {"pause", "pause musique", "mets pause"}:
        return IntentResult("spotify_pause", json.dumps({"action": "spotify_pause"}))
    if t in {"reprends", "reprends la musique", "continue la musique"}:
        return IntentResult("spotify_resume", json.dumps({"action": "spotify_resume"}))
    if t in {"suivant", "musique suivante", "piste suivante"}:
        return IntentResult("spotify_next", json.dumps({"action": "spotify_next"}))
    if t in {"précédent", "precedent", "musique précédente", "musique precedente"}:
        return IntentResult("spotify_prev", json.dumps({"action": "spotify_prev"}))
    if t.startswith(("joue ", "lance ")) and not any(
        marker in t for marker in ("la lumière", "lumière", "salon", "cuisine", "minuteur", "timer")
    ):
        query = re.sub(r"^(?:joue|lance)\s+", "", t).strip()
        if query:
            return IntentResult(
                "spotify_search_play",
                json.dumps({"action": "spotify_play", "query": query}, ensure_ascii=False),
            )
    return None


def _detect_network(t: str) -> Optional[IntentResult]:
    # ── Scan réseau ──
    if any(
        marker in t
        for marker in (
            "scanne le réseau", "scanne le reseau", "scan réseau", "scan reseau",
            "liste le wifi", "appareils connectés", "appareils connectes",
            "qui est sur le réseau", "qui est sur le reseau", "qui est connecté",
            "qui est connecte", "appareils sur le réseau", "appareils sur le reseau",
        )
    ):
        return IntentResult("network_scan", json.dumps({"action": "network_scan", "refresh": True}))
    # ── Liste des appareils connus ──
    if any(marker in t for marker in ("liste des appareils", "mes appareils", "appareils connus")):
        return IntentResult("device_list", json.dumps({"action": "device_list"}))
    # ── Ping ──
    if t.startswith("ping "):
        target = t[5:].strip()
        m = _RE_IP.search(t)
        if m:
            return IntentResult(
                "device_ping", json.dumps({"action": "device_ping", "target": m.group("ip")})
            )
        if target:
            return IntentResult(
                "device_ping", json.dumps({"action": "device_ping", "target": target})
            )
    # ── Wake-on-LAN ──
    if t.startswith(("réveille ", "reveille ", "wake ", "allume le pc", "allume le mac",
                     "allume l'ordinateur", "allume l ordinateur")):
        m = _RE_MAC.search(t)
        if m:
            return IntentResult(
                "wake_on_lan",
                json.dumps({"action": "wake_on_lan", "mac": m.group("mac").lower()}),
            )
        # Par nom d'appareil
        name = t.split(" ", 1)[-1].strip()
        if name and name not in ("pc", "mac", "l'ordinateur", "l ordinateur"):
            return IntentResult(
                "wake_on_lan", json.dumps({"action": "wake_on_lan", "name": name})
            )
    return None


def _detect_system(t: str) -> Optional[IntentResult]:
    if t in {"verrouille", "verrouille la session"}:
        return IntentResult("system_lock", json.dumps({"action": "system_control", "type": "lock"}))
    if t in {"veille", "mets en veille", "mets le mac en veille"}:
        return IntentResult(
            "system_sleep", json.dumps({"action": "system_control", "type": "sleep"})
        )
    if t == "vide la corbeille":
        return IntentResult(
            "system_empty_trash", json.dumps({"action": "system_control", "type": "empty_trash"})
        )
    if t == "coupe le son":
        return IntentResult("system_mute", json.dumps({"action": "system_control", "type": "mute"}))
    if t in {"rétablis le son", "retablis le son", "remets le son"}:
        return IntentResult(
            "system_unmute", json.dumps({"action": "system_control", "type": "unmute"})
        )
    if t in {"capture d'écran", "capture d ecran", "capture écran", "capture ecran"}:
        return IntentResult(
            "system_screenshot", json.dumps({"action": "system_control", "type": "screenshot"})
        )
    m = _RE_SYS_VOLUME.match(t)
    if m:
        return IntentResult(
            "system_volume",
            json.dumps(
                {"action": "system_control", "type": "volume", "percent": int(m.group("percent"))}
            ),
        )
    return None


def _detect_vision(t: str) -> Optional[IntentResult]:
    phone_markers = ("téléphone", "telephone", "iphone", "mobile")
    if any(marker in t for marker in phone_markers) and any(
        marker in t for marker in ("regarde", "caméra", "camera", "photo")
    ):
        return IntentResult(
            "vision_camera_phone",
            json.dumps(
                {
                    "action": "vision_camera_phone",
                    "question": "que vois-tu",
                    "facing": "environment",
                },
                ensure_ascii=False,
            ),
        )
    if t in {"regarde autour de toi", "que vois-tu", "que vois tu", "active la webcam"}:
        return IntentResult(
            "vision_camera_pc",
            json.dumps(
                {"action": "vision_camera_pc", "question": "que vois-tu"}, ensure_ascii=False
            ),
        )
    return None


def _detect_phone(t: str) -> Optional[IntentResult]:
    """Détecte les commandes de contrôle du téléphone."""
    # ── Vibration ──
    if any(m in t for m in ("fais vibrer", "fait vibrer", "vibre mon", "vibrer mon", "vibration")):
        return IntentResult(
            "phone_vibrate",
            json.dumps({"action": "phone_vibrate"}, ensure_ascii=False),
        )
    # ── Lampe torche ──
    if any(m in t for m in ("lampe torche", "lampe du téléphone", "lampe du telephone", "allume la lampe", "eteins la lampe", "éteins la lampe")):
        state_val = "off" if any(x in t for x in ("etein", "étein", "coupe")) else "on"
        return IntentResult(
            "phone_torch",
            json.dumps({"action": "phone_torch", "state": state_val}, ensure_ascii=False),
        )
        
    if "volume" in t and any(m in t for m in ("téléphone", "telephone", "tel")):
        return IntentResult(
            "phone_settings",
            json.dumps({"action": "phone_settings", "setting": "volume", "value": "change"}, ensure_ascii=False),
        )
    # ── Retrouver le téléphone ──
    if any(m in t for m in ("où est mon téléphone", "ou est mon téléphone", "ou est mon telephone",
                            "où est mon tel", "ou est mon tel",
                            "retrouve mon téléphone", "retrouve mon telephone", "retrouve mon tel",
                            "trouve mon téléphone", "trouve mon telephone", "trouve mon tel",
                            "sonne mon téléphone", "sonne mon telephone", "sonne mon tel",
                            "fais sonner")):
        return IntentResult(
            "phone_find",
            json.dumps({"action": "phone_find"}, ensure_ascii=False),
        )
    # ── GPS / Position ──
    if any(m in t for m in ("position du téléphone", "position du telephone", "position de mon tel",
                            "localise mon tel", "localise mon téléphone", "localise mon telephone",
                            "gps du téléphone", "gps du telephone", "gps de mon tel")):
        return IntentResult(
            "phone_gps",
            json.dumps({"action": "phone_gps"}, ensure_ascii=False),
        )
    # ── Batterie ──
    if any(m in t for m in ("batterie du téléphone", "batterie du telephone",
                            "batterie de mon tel", "batterie du tel",
                            "niveau de batterie", "charge du téléphone", "charge du telephone")):
        return IntentResult(
            "phone_battery",
            json.dumps({"action": "phone_battery"}, ensure_ascii=False),
        )
    # ── Alarme ──
    if any(m in t for m in ("alarme sur mon téléphone", "alarme sur mon telephone",
                            "alarme sur le téléphone", "alarme sur le telephone",
                            "alarme du téléphone", "alarme du telephone", "alarme du tel")):
        return IntentResult(
            "phone_alarm",
            json.dumps({"action": "phone_alarm"}, ensure_ascii=False),
        )
    # ── Presse-papier ──
    if any(m in t for m in ("presse-papier du téléphone", "presse-papier du telephone",
                            "clipboard du tel",
                            "copie sur mon téléphone", "copie sur mon telephone",
                            "presse papier du tel")):
        return IntentResult(
            "phone_clipboard_read",
            json.dumps({"action": "phone_clipboard_read"}, ensure_ascii=False),
        )
    # ── Ouvrir une app sur le téléphone ──
    phone_words = ("téléphone", "telephone", "tel", "iphone", "mobile")
    open_words = ("ouvre", "lance", "démarre", "demarre", "mets")
    if any(ow in t for ow in open_words) and any(pw in t for pw in phone_words):
        # Extraire le nom de l'app : "ouvre netflix sur mon telephone"
        import re as _re
        m = _re.search(r"(?:ouvre|lance|démarre|demarre|mets)\s+(.+?)\s+(?:sur|de|du)\s+(?:mon|le|la)\s+(?:téléphone|telephone|tel|iphone|mobile)", t)
        if m:
            app_name = m.group(1).strip()
            if app_name:
                return IntentResult(
                    "phone_open_app",
                    json.dumps({"action": "phone_open_app", "app": app_name}, ensure_ascii=False),
                )
    return None


def _detect_knowledge(t: str) -> Optional[IntentResult]:
    # ── Notes rapides (Obsidian/SiYuan) ──
    note_prefixes = ("note ", "note: ", "note :", "capture ", "mémorise ", "memorise ")
    for prefix in note_prefixes:
        if t.startswith(prefix):
            content = t[len(prefix):].strip()
            if content:
                return IntentResult(
                    "note_capture",
                    json.dumps({"action": "note_capture", "content": content}, ensure_ascii=False),
                )
    # ── Recherche dans les notes ──
    note_search_markers = (
        "cherche dans mes notes", "cherche dans mes note",
        "chercher dans mes notes", "dans mes notes",
        "dans mon vault", "dans mon carnet",
    )
    for marker in note_search_markers:
        if marker in t:
            query = t.replace(marker, "").strip(" ,.")
            if query:
                return IntentResult(
                    "note_search",
                    json.dumps({"action": "note_search", "query": query}, ensure_ascii=False),
                )
    # ── Actualités / Connaissances ──
    if any(
        marker in t
        for marker in ("actualités", "actualites", "dernières nouvelles", "dernieres nouvelles")
    ):
        return IntentResult(
            "news", json.dumps({"action": "knowledge_query", "question": t}, ensure_ascii=False)
        )
    if t.startswith(("c'est quoi ", "c est quoi ", "qui est ", "qu'est-ce que ", "qu est ce que ")):
        return IntentResult(
            "knowledge_query",
            json.dumps({"action": "knowledge_query", "question": t}, ensure_ascii=False),
        )
    return None


def _detect_tv(t: str) -> Optional[IntentResult]:
    # ── Contrôle de la TV (ADB) ──
    tv_words = ("la tv", "la télé", "la tele", "la television", "la télévision")
    if any(tw in t for tw in tv_words):
        # 1. YouTube TV
        import re
        m = re.search(r"(?:lance|joue|mets|cherche)\s+(.+?)\s+(?:sur\s+(?:le\s+)?youtube\s+(?:de\s+)?la\s+tv|sur\s+youtube\s+tv)", t)
        if m:
            query = m.group(1).strip()
            return IntentResult(
                "adb_youtube_tv",
                json.dumps({"action": "adb_youtube_tv", "query": query}, ensure_ascii=False),
            )
            
        # 2. Télécommande basique
        action_words = ("baisse", "monte", "plus", "moins", "pause", "play", "lecture", "augmente", "diminue", "volume",
                        "accueil", "home", "eteins", "éteins", "allume", "retour", "gauche", "droite", "haut", "bas", "ok", "valider")
        for aw in action_words:
            if aw in t:
                return IntentResult(
                    "adb_tv_control",
                    json.dumps({"action": "adb_tv_control", "action_tv": aw}, ensure_ascii=False),
                )
    return None


def detect(texte: str) -> Optional[IntentResult]:
    """Tente une reconnaissance locale. Renvoie None si incertain."""
    if not texte:
        return None
    t = _norm(texte)
    if not t:
        return None

    # --- Domotique ---
    m = _RE_ALLUME.match(t)
    if m:
        p = PIECES_ALIAS.get(m.group("piece"))
        return IntentResult(
            "allumer", json.dumps({"action": "ha_lumiere", "piece": p, "etat": "on"})
        )

    m = _RE_ETEINS.match(t)
    if m:
        p = PIECES_ALIAS.get(m.group("piece"))
        return IntentResult(
            "eteindre", json.dumps({"action": "ha_lumiere", "piece": p, "etat": "off"})
        )

    m = _RE_THERMOSTAT.match(t)
    if m:
        temperature = float(m.group("temperature").replace(",", "."))
        value = int(temperature) if temperature.is_integer() else temperature
        return IntentResult(
            "thermostat",
            json.dumps({"action": "ha_thermostat", "temperature": value}, ensure_ascii=False),
        )

    # --- Heure / Date ---
    if _RE_HEURE.match(t):
        return IntentResult("heure", f"Il est {time.strftime('%Hh%M')}, Monsieur.")
    if _RE_DATE.match(t):
        return IntentResult("date", f"Nous sommes le {time.strftime('%A %d %B %Y')}.")

    # --- Météo ---
    meteo = _detect_meteo(t)
    if meteo:
        return meteo

    media = _detect_media(t)
    if media:
        return media

    email = _detect_email(t)
    if email:
        return email

    # --- Vision / Réseau / Système / Téléphone / TV / Spotify / Connaissance ---
    for detector in (
        _detect_vision,
        _detect_network,
        _detect_system,
        _detect_phone,
        _detect_tv,
        _detect_spotify,
        _detect_knowledge,
    ):
        result = detector(t)
        if result:
            return result

    # --- Timers ---
    m = _RE_TIMER.match(t)
    if m:
        n = int(m.group("n"))
        sec = _unite_to_seconds(n, m.group("u"))
        return IntentResult("timer_set", _timer_payload(sec, m.group("label") or "minuteur"))

    m = _RE_RAPPEL.match(t)
    if m:
        n = int(m.group("n"))
        sec = _unite_to_seconds(n, m.group("u"))
        return IntentResult(
            "rappel_set", _timer_payload(sec, m.group("label") or "rappel", kind="rappel")
        )

    # --- Système ---
    if _RE_SYS_STATS.match(t):
        return IntentResult("system_stats", json.dumps({"action": "system_stats"}))

    return None
