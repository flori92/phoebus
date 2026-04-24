"""Découpeur de phrases tolérant, adapté à la synthèse vocale FR.

Règles :
- Coupe sur `. ! ?` suivis d'un espace/EOL.
- Ne coupe PAS sur les abréviations usuelles : M. Mme Dr Pr St Ste
  Mlle MM. etc. p. ex. c.-à-d. i.e. e.g.
- Ne coupe pas sur les décimales (`3.14`) ni sur les ordinaux (`21e`).
- Une phrase doit faire au moins `min_len` caractères pour être coupée
  (évite les fragments dégénérés).
- Si aucun séparateur n'est trouvé, renvoie [texte].

Utilisé par voice.parler pour pipeliner la synthèse, et par ai.py pour
décider quand "parler" pendant un streaming LLM.
"""
import re

_ABBREV = {
    "m", "mme", "mlle", "mm", "mr", "dr", "pr", "st", "ste",
    "etc", "cf", "ex", "c.-à-d", "i.e", "e.g", "p. ex", "p.ex",
    "n°", "no",
}

_RE_SENTENCE_END = re.compile(r"([.!?…])\s+")


def _is_abbrev(token: str) -> bool:
    return token.lower().rstrip(".") in _ABBREV


def split_streaming(buffer: str, min_len: int = 12) -> tuple[list[str], str]:
    """Version streaming : renvoie (phrases_completes, reste_inacheve).

    Une phrase "complète" DOIT se terminer par un séparateur `.!?…` SUIVI d'un
    espace. Ça garantit qu'on n'émet pas prématurément un mot tronqué côté
    LLM. Le reliquat reste en buffer jusqu'au prochain appel.
    """
    if not buffer:
        return [], ""
    sentences = []
    last = 0
    for m in re.finditer(r"[.!?…]+\s", buffer):
        end = m.end()
        candidate = buffer[last:end].strip()
        if len(candidate) < min_len:
            continue
        # Évite les abréviations (dernier mot avant le point).
        head = candidate[:-1]
        word_before = re.search(r"(\S+)$", head)
        if word_before and _is_abbrev(word_before.group(1)):
            continue
        sentences.append(candidate)
        last = end
    return sentences, buffer[last:]


def split(texte: str, min_len: int = 12) -> list[str]:
    """Découpe `texte` en phrases complètes.

    Exemple :
        "Bonjour Floriace. M. Favi est arrivé. Que souhaitez-vous ?"
        → ["Bonjour Floriace.", "M. Favi est arrivé.", "Que souhaitez-vous ?"]
    """
    if not texte:
        return []

    s = texte.strip()
    if not s:
        return []

    phrases = []
    last = 0
    for m in _RE_SENTENCE_END.finditer(s):
        end = m.end()
        candidate = s[last:end].strip()
        if len(candidate) < min_len:
            continue

        # Vérifie qu'on n'est pas sur une abréviation ("M.", "Dr.").
        # On regarde le dernier "mot" avant le point.
        head = s[last : m.start() + 1]  # inclut le séparateur
        word_match = re.search(r"(\S+)$", head[:-1])  # mot avant le séparateur
        if word_match:
            word = word_match.group(1)
            if _is_abbrev(word):
                continue

        # Pas une décimale (chiffres autour du point).
        if m.start() > 0 and s[m.start() - 1].isdigit():
            # ex: "3.14 est pi." → on ne coupe pas sur le 3.14
            # Heuristique : si c'est ".", regarde ce qu'il y a après l'espace
            if m.group(1) == "." and end < len(s) and s[end].isdigit():
                continue

        phrases.append(candidate)
        last = end

    # Reliquat final (sans ponctuation terminale).
    reliquat = s[last:].strip()
    if reliquat:
        if phrases and len(reliquat) < min_len:
            # Trop court pour être une phrase : on le colle à la précédente.
            phrases[-1] = phrases[-1] + " " + reliquat
        else:
            phrases.append(reliquat)

    return phrases if phrases else [s]
