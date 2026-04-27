"""Dispatcher d'intention local — fast-path des commandes évidentes.

Objectif : court-circuiter l'appel LLM pour les commandes simples et répétitives
(allumer/éteindre une pièce, demander l'heure ou la date, ouvrir un dossier
connu, etc.). Latence : ~50 ms au lieu de ~1,2 s round-trip cloud.

Principe :
- Une série de patterns regex nommés reconnaît l'intention.
- Si un pattern matche avec confiance suffisante, on renvoie directement
  le bloc JSON ou la réponse texte, comme si le LLM l'avait produit.
- Si ambigu ou non reconnu, on renvoie None → le flux retombe sur le LLM.

Le dispatcher reste volontairement conservateur : on préfère passer par le
LLM plutôt que de deviner mal.
"""
import re
import time
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
    "chambre parentale": "chambre",
    "bureau": "bureau",
    "couloir": "couloir",
    "entree": "entree",
    "entrée": "entree",
    "salle de bain": "salle_de_bain",
    "salle de bains": "salle_de_bain",
    "sdb": "salle_de_bain",
    "toilettes": "toilettes",
    "wc": "toilettes",
    "garage": "garage",
    "cave": "cave",
    "terrasse": "terrasse",
    "jardin": "jardin",
    "exterieur": "exterieur",
    "extérieur": "exterieur",
}

_PIECE_PATTERN = "(?:" + "|".join(sorted(PIECES_ALIAS.keys(), key=len, reverse=True)) + ")"
_WAKE_PREFIX = r"(?:(?:phoebus|phébus|fébus|febus|feubus|rebus)[, ]*)?"


# ── Patterns ──────────────────────────────────────────────────────────────

_RE_ALLUME = re.compile(
    rf"^{_WAKE_PREFIX}(?:allume|éclaire|eclaire|lumiere|lumière)"
    rf"(?:\s+(?:la lumière|la lumiere|les lumières|les lumieres))?"
    rf"(?:\s+(?:du|de la|de l'|dans le|dans la|dans l'|au|à la|la|le|l'|les))?"
    rf"\s+(?P<piece>{_PIECE_PATTERN})$"
)

_RE_ETEINS = re.compile(
    rf"^{_WAKE_PREFIX}(?:éteins|eteins|coupe)"
    rf"(?:\s+(?:la lumière|la lumiere|les lumières|les lumieres))?"
    rf"(?:\s+(?:du|de la|de l'|dans le|dans la|dans l'|au|à la|la|le|l'|les))?"
    rf"\s+(?P<piece>{_PIECE_PATTERN})$"
)

_RE_HEURE = re.compile(
    rf"^{_WAKE_PREFIX}(?:quelle heure est[- ]il"
    r"|il est quelle heure"
    r"|tu as l[' ]heure"
    r"|donne(?:-| )moi l[' ]heure"
    r"|dis(?:-| )moi l[' ]heure)$"
)

_RE_DATE = re.compile(
    rf"^{_WAKE_PREFIX}(?:quel jour (?:sommes|on est|est)(?:[- ]nous)?"
    r"|on est quel jour"
    r"|quelle (?:est la )?date"
    r"|la date du jour)$"
)

_RE_METEO = re.compile(
    rf"^{_WAKE_PREFIX}(?:(?:quel temps|quelle météo|la météo|le temps|il fait quoi)"
    r"(?:\s+(?:fait[- ]il|est[- ]il))?"
    r"(?:\s+(?:à|a|en|sur|au|aux)\s+(?P<ville>[a-zà-ÿ' -]+))?)$"
)

_RE_THERMOSTAT = re.compile(
    rf"^{_WAKE_PREFIX}(?:mets|règle|regle|passe)\s+(?:le\s+)?thermostat\s+(?:à|a|sur)\s+(?P<t>\d{{1,2}})(?:\s*degrés?)?$"
)

_RE_SCENE = re.compile(
    rf"^{_WAKE_PREFIX}(?:lance|active|démarre|demarre)\s+(?:la\s+)?(?:scène|scene|mode)\s+(?P<nom>[a-zà-ÿ' -]+)$"
)

_RE_MEMORISER = re.compile(
    rf"^{_WAKE_PREFIX}(?:retiens|note|mémorise|memorise|souviens[- ]toi)\s+(?:que\s+)?(?P<contenu>.+)$"
)

_RE_LISTER_MEM = re.compile(
    rf"^{_WAKE_PREFIX}(?:liste|montre|donne[- ]moi)\s+(?:ta|la)\s+(?:mémoire|memoire|liste)$"
)

_RE_MODE_IRON_MAN_ON = re.compile(
    rf"^{_WAKE_PREFIX}(?:active|lance|démarre|demarre)\s+(?:le\s+)?mode\s+iron\s*man$"
)
_RE_MODE_IRON_MAN_OFF = re.compile(
    rf"^{_WAKE_PREFIX}(?:désactive|desactive|coupe|arrête|arrete|stop)\s+(?:le\s+)?mode\s+iron\s*man$"
)

_RE_SYS_STATS = re.compile(
    rf"^{_WAKE_PREFIX}(?:"
    r"état du système|etat du systeme|santé matérielle|sante materielle"
    r"|utilisation (?:du\s+)?cpu|niveau (?:de\s+)?batterie"
    r"|combien de batterie"
    r")$"
)

_RE_NET_INFO = re.compile(
    rf"^{_WAKE_PREFIX}(?:"
    r"où es-tu|où (?:on est|on se trouve)|position réseau|infos? réseau"
    r"|mon adresse ip|ton adresse ip|quelle est (?:ma|ta) position"
    r")$"
)

# ── Contrôle du volume système ───────────────────────────────────────────
_RE_VOLUME_UP = re.compile(rf"^{_WAKE_PREFIX}(?:monte|augmente|augmentez)\s+(?:le\s+)?(?:volume|son)$")
_RE_VOLUME_DOWN = re.compile(rf"^{_WAKE_PREFIX}(?:baisse|diminue|diminuez)\s+(?:le\s+)?(?:volume|son)$")
_RE_VOLUME_MUTE = re.compile(rf"^{_WAKE_PREFIX}(?:coupe|coupez|mute)\s+(?:le\s+)?(?:volume|son)$")

# ── Timers et rappels persistants ──────────────────────────────────────────
_RE_TIMER = re.compile(
    rf"^{_WAKE_PREFIX}(?:mets|lance|démarre|demarre|programme|active)?\s*"
    rf"(?:un\s+)?(?:minuteur|chrono|chronomètre|chronometre|timer)\s*"
    rf"(?:de\s+|sur\s+|à\s+|de\s*)?"
    rf"(?P<n>\d{{1,3}})\s*"
    rf"(?P<u>s(?:ec(?:onde)?s?)?|min(?:ute)?s?|h(?:eure)?s?)?"
    rf"(?:\s+pour\s+(?P<label>.+))?$"
)

_RE_RAPPEL = re.compile(
    rf"^{_WAKE_PREFIX}(?:rappelle[- ]?moi)\s+"
    rf"(?:(?:de\s+|d['’]\s*)?(?P<label>[^,]+?)\s+)?"
    rf"dans\s+(?P<n>\d{{1,3}})\s*"
    rf"(?P<u>s(?:ec(?:onde)?s?)?|min(?:ute)?s?|h(?:eure)?s?)"
    rf"(?:\s+(?:de\s+|d['’]\s*)?(?P<label2>.+))?$"
)

_RE_LISTER_TIMERS = re.compile(
    rf"^{_WAKE_PREFIX}(?:liste|montre|affiche)\s+(?:les\s+)?"
    rf"(?:minuteurs?|timers?|rappels?|chronom[èe]tres?)$"
)

# ── Spotify (intents fast-path) ────────────────────────────────────────────
_RE_SPOT_PLAY = re.compile(rf"^{_WAKE_PREFIX}(?:reprends|lance|play|joue|reprise)(?:\s+la\s+musique| la playlist)?$")
_RE_SPOT_PAUSE = re.compile(rf"^{_WAKE_PREFIX}(?:pause|met(?:s)?\s+(?:en\s+)?pause|arr[êe]te\s+la\s+musique|stop\s+la\s+musique)$")
_RE_SPOT_NEXT = re.compile(rf"^{_WAKE_PREFIX}(?:suivante|(?:morceau|chanson|titre)\s+suivant|next)$")
_RE_SPOT_PREV = re.compile(rf"^{_WAKE_PREFIX}(?:pr[ée]c[ée]dente|(?:morceau|chanson|titre)\s+pr[ée]c[ée]dent|previous)$")
_RE_SPOT_NOW = re.compile(rf"^{_WAKE_PREFIX}(?:c(?:'|\s?)est quoi|qu(?:'|\s)est-ce (?:qui|que)\s+(?:\w+\s+){{0,3}})?\s*(?:ce morceau|cette (?:chanson|musique)|le (?:morceau|titre))(?:\s+qui\s+passe)?$")
_RE_SPOT_VOL = re.compile(rf"^{_WAKE_PREFIX}(?:mets|règle|regle|passe)\s+(?:le\s+)?volume\s+(?:spotify\s+)?(?:à|a|sur)\s+(?P<v>\d{{1,3}})(?:\s*%| pour cent)?$")
_RE_SPOT_SEARCH = re.compile(rf"^{_WAKE_PREFIX}(?:mets|joue|lance|écoute|ecoute|play)\s+(?:la (?:chanson|musique)|le morceau|le titre)?\s*(?P<q>.+)$")

# ── Caméras : PC webcam / téléphone / caméra IP ────────────────────────────
# "regarde autour de toi" / "que vois-tu" / "regarde ce que je te montre"
_RE_CAM_PC = re.compile(
    rf"^{_WAKE_PREFIX}(?:"
    rf"regarde\s+(?:autour|ici|devant|ce que je te montre|ce qu(?:i|e)\s+il y a)"
    rf"|que (?:vois|regardes)[- ]tu"
    rf"|qu(?:'|\s)est[- ]ce qu(?:i|e)\s+il y a (?:devant|ici|autour)"
    rf"|active\s+(?:la\s+)?(?:webcam|cam[ée]ra)(?:\s+du pc| de l'ordinateur)?"
    rf"|prends? une photo (?:de la pi[èe]ce|de mon environnement)"
    rf")(?:\s+(?P<question>.+))?$"
)

_RE_CAM_PHONE = re.compile(
    rf"^{_WAKE_PREFIX}(?:"
    rf"regarde\s+(?:avec|via|sur|depuis)\s+(?:mon\s+)?(?:t[ée]l[ée]phone|portable|mobile|iphone|smartphone)"
    rf"|utilise\s+(?:la\s+cam[ée]ra\s+(?:de\s+)?)?(?:mon\s+)?(?:t[ée]l[ée]phone|portable|mobile|iphone|smartphone)"
    rf"|prends? une photo (?:avec|via)\s+(?:mon\s+)?(?:t[ée]l[ée]phone|portable|mobile|iphone|smartphone)"
    rf")(?:\s+(?P<question>.+))?$"
)

_RE_CAM_IP = re.compile(
    rf"^{_WAKE_PREFIX}(?:regarde|montre[- ]moi)\s+(?:la\s+)?cam[ée]ra\s+(?P<lieu>[a-zà-ÿ' -]+)$"
)


def _unite_to_seconds(n: int, unit: str) -> int:
    u = (unit or "min").lower()
    if u.startswith("s"):
        return n
    if u.startswith("h"):
        return n * 3600
    return n * 60


# ── Résultat ──────────────────────────────────────────────────────────────

class IntentResult:
    """Conteneur immuable pour une intention reconnue.

    `reply` est soit du texte à dire directement, soit une chaîne contenant
    un ou plusieurs blocs JSON (compatible avec `traiter_reponse_ia`).
    """
    __slots__ = ("name", "reply", "confidence")

    def __init__(self, name: str, reply: str, confidence: float = 1.0):
        self.name = name
        self.reply = reply
        self.confidence = confidence


def _piece_canonique(raw: str) -> str:
    return PIECES_ALIAS.get(raw.strip(), raw.strip())


# ── Dispatcher ────────────────────────────────────────────────────────────

def detect(texte: str) -> Optional[IntentResult]:
    """Tente une reconnaissance locale. Renvoie None si incertain."""
    if not texte:
        return None
    t = _norm(texte)
    if not t:
        return None

    m = _RE_ALLUME.match(t)
    if m:
        piece = _piece_canonique(m.group("piece"))
        return IntentResult(
            "allumer",
            '{"action": "ha_lumiere", "piece": "' + piece + '", "etat": "on"}',
        )
    m = _RE_ETEINS.match(t)
    if m:
        piece = _piece_canonique(m.group("piece"))
        return IntentResult(
            "eteindre",
            '{"action": "ha_lumiere", "piece": "' + piece + '", "etat": "off"}',
        )

    m = _RE_THERMOSTAT.match(t)
    if m:
        temp = int(m.group("t"))
        if 5 <= temp <= 30:
            return IntentResult(
                "thermostat",
                '{"action": "ha_thermostat", "temperature": ' + str(temp) + "}",
            )

    m = _RE_SCENE.match(t)
    if m:
        nom = m.group("nom").strip()
        return IntentResult(
            "scene",
            '{"action": "ha_scene", "nom": "' + nom + '"}',
        )

    if _RE_HEURE.match(t):
        heure = time.strftime("%Hh%M")
        return IntentResult("heure", f"Il est {heure}, Monsieur.")
    if _RE_DATE.match(t):
        jour = time.strftime("%A %d %B %Y")
        return IntentResult("date", f"Nous sommes le {jour}.")

    m = _RE_METEO.match(t)
    if m:
        ville = (m.group("ville") or "").strip()
        if ville:
            return IntentResult(
                "meteo_ville",
                '{"action": "meteo", "ville": "' + ville + '"}',
            )
        return IntentResult("meteo", '{"action": "meteo"}')

    m = _RE_MEMORISER.match(t)
    if m:
        contenu = m.group("contenu").strip()
        if " est " in contenu:
            cle, val = contenu.split(" est ", 1)
            return IntentResult(
                "memoriser",
                f'{{"action": "memoriser", "cle": "{cle.strip()}", "valeur": "{val.strip()}"}}',
            )
    if _RE_LISTER_MEM.match(t):
        return IntentResult("lister_memoire", '{"action": "lister_memoire"}')

    if _RE_MODE_IRON_MAN_ON.match(t):
        return IntentResult(
            "mode_iron_man_on", '{"action": "mode_iron_man", "etat": "on"}'
        )
    if _RE_MODE_IRON_MAN_OFF.match(t):
        return IntentResult(
            "mode_iron_man_off", '{"action": "mode_iron_man", "etat": "off"}'
        )

    if _RE_SYS_STATS.match(t):
        return IntentResult("system_stats", '{"action": "system_stats"}')
    
    if _RE_NET_INFO.match(t):
        return IntentResult("network_info", '{"action": "network_info"}')

    # ── Volume Système ────────────────────────────────────────────────────
    if _RE_VOLUME_UP.match(t):
        return IntentResult("volume_up", '{"action": "system_control", "type": "volume_up"}')
    if _RE_VOLUME_DOWN.match(t):
        return IntentResult("volume_down", '{"action": "system_control", "type": "volume_down"}')
    if _RE_VOLUME_MUTE.match(t):
        return IntentResult("volume_mute", '{"action": "system_control", "type": "mute"}')

    # ── Timer ─────────────────────────────────────────────────────────────
    m = _RE_TIMER.match(t)
    if m:
        n = int(m.group("n"))
        unit = m.group("u") or "min"
        seconds = _unite_to_seconds(n, unit)
        m_val = seconds // 60
        s_val = seconds % 60
        label = (m.group("label") or "minuteur").strip()
        import json as _json
        payload = {"action": "timer", "minutes": m_val, "secondes": s_val, "label": label}
        return IntentResult("timer", _json.dumps(payload, ensure_ascii=False))

    # ── Rappel ────────────────────────────────────────────────────────────
    m = _RE_RAPPEL.match(t)
    if m:
        n = int(m.group("n"))
        unit = m.group("u") or "min"
        seconds = _unite_to_seconds(n, unit)
        label = (m.group("label") or m.group("label2") or "").strip().rstrip(".")
        import json as _json
        payload = {"action": "timer_set", "duration_s": seconds, "kind": "rappel"}
        if label:
            payload["label"] = label
        return IntentResult("rappel_set", _json.dumps(payload, ensure_ascii=False))

    if _RE_LISTER_TIMERS.match(t):
        return IntentResult("timer_list", '{"action": "timer_list"}')

    # ── Playwright : ouvre un site connu ─────────────────────────────────
    try:
        from PHOEBUS.playwright_skill import parse_open_url_intent
        url = parse_open_url_intent(t)
        if url:
            import json as _json
            return IntentResult(
                "playwright_run",
                _json.dumps({"action": "playwright_run", "url": url}, ensure_ascii=False),
            )
    except Exception:
        pass

    # ── Spotify ───────────────────────────────────────────────────────────
    if _RE_SPOT_PAUSE.match(t):
        return IntentResult("spotify_pause", '{"action": "spotify_pause"}')
    if _RE_SPOT_PLAY.match(t):
        return IntentResult("spotify_play", '{"action": "spotify_play"}')
    if _RE_SPOT_NEXT.match(t):
        return IntentResult("spotify_next", '{"action": "spotify_next"}')
    if _RE_SPOT_PREV.match(t):
        return IntentResult("spotify_previous", '{"action": "spotify_previous"}')
    if _RE_SPOT_NOW.match(t):
        return IntentResult("spotify_now_playing", '{"action": "spotify_now_playing"}')
    m = _RE_SPOT_VOL.match(t)
    if m:
        v = int(m.group("v"))
        if 0 <= v <= 100:
            return IntentResult("spotify_volume", '{"action": "spotify_volume", "volume": ' + str(v) + "}")
    m = _RE_SPOT_SEARCH.match(t)
    if m:
        q = m.group("q").strip()
        # Filtre : "mets le salon" ne doit PAS déclencher Spotify. On rejette
        # si la requête correspond à une pièce connue.
        if q and q not in PIECES_ALIAS and len(q) >= 3:
            import json as _json
            return IntentResult(
                "spotify_search_play",
                _json.dumps({"action": "spotify_search_play", "query": q}, ensure_ascii=False),
            )

    # ── Caméras ───────────────────────────────────────────────────────────
    m = _RE_CAM_PHONE.match(t)
    if m:
        question = (m.group("question") or "").strip()
        import json as _json
        payload = {"action": "vision_camera_phone"}
        if question:
            payload["question"] = question
        return IntentResult("vision_camera_phone",
                            _json.dumps(payload, ensure_ascii=False))

    m = _RE_CAM_PC.match(t)
    if m:
        question = (m.group("question") or "").strip()
        import json as _json
        payload = {"action": "vision_camera_pc"}
        if question:
            payload["question"] = question
        return IntentResult("vision_camera_pc",
                            _json.dumps(payload, ensure_ascii=False))

    m = _RE_CAM_IP.match(t)
    if m:
        # On laisse le LLM ou la config résoudre le nom → URL.
        lieu = (m.group("lieu") or "").strip()
        import json as _json
        payload = {"action": "vision_camera_ip", "label": lieu}
        return IntentResult("vision_camera_ip",
                            _json.dumps(payload, ensure_ascii=False))

    return None
