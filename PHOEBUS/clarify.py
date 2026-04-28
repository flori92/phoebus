"""Clarification / auto-correction de PHOEBUS.

Deux responsabilités :
1. Détecter qu'une transcription micro est probablement cassée / incomprise
   (trop courte, mot seul, charabia) afin que PHOEBUS redemande plutôt
   que d'inventer.
2. Détecter qu'une demande est ambiguë avant de déclencher une action,
   pour que PHOEBUS pose une question de clarification courte.
"""
import re


_MOTS_COURTS_IGNORE = {
    "oui", "non", "ok", "ouais", "bon", "stop", "merci", "bien",
    "chut", "hop", "ah", "oh", "eh", "euh", "hein",
}

_TOKENS_BLABLA = re.compile(r"[a-zA-ZÀ-ÿ']+")
_MEDIA_NOISE_PATTERNS = (
    r"^merci d avoir regarde\b",
    r"^merci de nous regarder\b",
    r"^merci de votre ecoute\b",
    r"^sous titr(?:age|es?)\b",
    r"\bst\s*\d+\b",
    r"\bsubtitles?\b",
    r"\bcaptions?\b",
    r"\bamara\b",
    r"\byoutube\b",
    r"\babonnez vous\b",
    r"\bcliquez ici\b",
)


def _compact_transcription(texte: str) -> str:
    from PHOEBUS.utils import normalize_text

    t = normalize_text(texte)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def transcription_bruit_media(texte: str) -> bool:
    """Détecte les transcriptions typiques de vidéo/sous-titres à ignorer."""
    if not texte:
        return True
    raw = str(texte).strip()
    if not raw or set(raw) <= {".", "…", " "}:
        return True

    t = _compact_transcription(raw)
    if not t:
        return True
    return any(re.search(pattern, t, re.IGNORECASE) for pattern in _MEDIA_NOISE_PATTERNS)


def transcription_incertaine(texte: str) -> bool:
    """Renvoie True si on pense que le STT a mal compris et qu'il vaut mieux redemander."""
    if not texte:
        return True
    t = texte.strip().lower()
    if len(t) < 3:
        return True
    tokens = _TOKENS_BLABLA.findall(t)
    # Un seul mot court et non significatif → probablement un bruit.
    if len(tokens) == 1 and tokens[0] in _MOTS_COURTS_IGNORE:
        return False  # valide mais court, pas un charabia
    if len(tokens) == 1 and len(tokens[0]) < 4:
        return True
    # Essentiellement des symboles / chiffres.
    if not tokens:
        return True
    return False


_SUJETS_AMBIGUS = (
    "lumière", "lumiere", "prise", "scène", "scene",
    "fichier", "dossier", "document",
)


def demande_ambigue(texte: str) -> bool:
    """Heuristique légère : on soupçonne une demande imprécise qui mériterait
    une question de précision avant d'exécuter."""
    if not texte:
        return False
    t = texte.lower()
    # "allume" sans cible, "ouvre" sans nom, etc.
    motifs = [
        r"\ballume\b(?!.*\b(salon|cuisine|chambre|bureau|couloir|cave|garage|entrée|salle|terrasse)\b)",
        r"\béteins\b(?!.*\b(salon|cuisine|chambre|bureau|couloir|cave|garage|entrée|salle|terrasse)\b)",
        r"\bouvre\b(?!.*\b(dossier|fichier|bureau|document|page|url|lien)\b)",
        r"\bfais\s+ça\b",
        r"\bpareil\b",
    ]
    for m in motifs:
        if re.search(m, t):
            return True
    return False


def question_pour_clarifier(texte: str) -> str:
    """Formule une question de clarification courte et naturelle."""
    t = (texte or "").lower()
    if "allume" in t or "éteins" in t or "eteins" in t:
        return "Dans quelle pièce, Monsieur ?"
    if "ouvre" in t:
        return "Qu'est-ce que vous voulez que j'ouvre exactement ?"
    if "fais ça" in t or "pareil" in t:
        return "Vous faites référence à quoi précisément ?"
    return "Vous pouvez préciser, Monsieur ?"
