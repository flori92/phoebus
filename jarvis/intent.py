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


# ── Patterns ──────────────────────────────────────────────────────────────

_RE_ALLUME = re.compile(
    rf"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:allume|éclaire|eclaire|lumiere|lumière)"
    rf"(?:\s+(?:la lumière|la lumiere|les lumières|les lumieres))?"
    rf"(?:\s+(?:du|de la|de l'|dans le|dans la|dans l'|au|à la|la|le|l'|les))?"
    rf"\s+(?P<piece>{_PIECE_PATTERN})$"
)

_RE_ETEINS = re.compile(
    rf"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:éteins|eteins|coupe)"
    rf"(?:\s+(?:la lumière|la lumiere|les lumières|les lumieres))?"
    rf"(?:\s+(?:du|de la|de l'|dans le|dans la|dans l'|au|à la|la|le|l'|les))?"
    rf"\s+(?P<piece>{_PIECE_PATTERN})$"
)

_RE_HEURE = re.compile(
    r"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:quelle heure est[- ]il"
    r"|il est quelle heure"
    r"|tu as l[' ]heure"
    r"|donne(?:-| )moi l[' ]heure"
    r"|dis(?:-| )moi l[' ]heure)$"
)

_RE_DATE = re.compile(
    r"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:quel jour (?:sommes|on est|est)(?:[- ]nous)?"
    r"|on est quel jour"
    r"|quelle (?:est la )?date"
    r"|la date du jour)$"
)

_RE_METEO = re.compile(
    r"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:(?:quel temps|quelle météo|la météo|le temps|il fait quoi)"
    r"(?:\s+(?:fait[- ]il|est[- ]il))?"
    r"(?:\s+(?:à|a|en|sur|au|aux)\s+(?P<ville>[a-zà-ÿ' -]+))?)$"
)

_RE_THERMOSTAT = re.compile(
    r"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:mets|règle|regle|passe)\s+(?:le\s+)?thermostat\s+(?:à|a|sur)\s+(?P<t>\d{1,2})(?:\s*degrés?)?$"
)

_RE_SCENE = re.compile(
    r"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:lance|active|démarre|demarre)\s+(?:la\s+)?(?:scène|scene|mode)\s+(?P<nom>[a-zà-ÿ' -]+)$"
)

_RE_MEMORISER = re.compile(
    r"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:retiens|note|mémorise|memorise|souviens[- ]toi)\s+(?:que\s+)?(?P<contenu>.+)$"
)

_RE_LISTER_MEM = re.compile(
    r"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:liste|montre|donne[- ]moi)\s+(?:ta|la)\s+(?:mémoire|memoire|liste)$"
)

_RE_MODE_IRON_MAN_ON = re.compile(
    r"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:active|lance|démarre|demarre)\s+(?:le\s+)?mode\s+iron\s*man$"
)
_RE_MODE_IRON_MAN_OFF = re.compile(
    r"^(?:phoebus|phébus|fébus|febus|feubus|rebus|jarvis[, ]*)?(?:désactive|desactive|coupe|arrête|arrete|stop)\s+(?:le\s+)?mode\s+iron\s*man$"
)


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

    return None
