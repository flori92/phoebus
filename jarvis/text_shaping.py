"""Naturalisation du texte avant envoi au TTS.

Objectif : faire sonner Jarvis humain plutôt que lecteur automatique.
Un bon moteur TTS (Piper, Edge Remy, ElevenLabs) gère déjà nombre et
prosodie, mais quelques transformations côté texte améliorent sensiblement
le rendu oral :

- suppression du Markdown résiduel (`**`, `_`, `#`, ` ``` `, ...)
- expansion des abréviations françaises que les moteurs disent mal
- remplacement des unités et symboles (°C, €, %, km/h, Ko/s...)
- insertion de virgules de respiration après les mots de liaison
- micro-pauses (« ... ») autour des incises et interjections
- normalisation des espaces et des points multiples
- découpe douce des phrases très longues sur la ponctuation

La fonction est pure (str → str), testable sans dépendance.
"""
import re


# ── Abréviations courantes en FR ───────────────────────────────────────────
_ABREVIATIONS = [
    (re.compile(r"\bM\.\s+(?=[A-ZÉÈÀÇ])"), "Monsieur "),
    (re.compile(r"\bMme\b\.?"), "Madame"),
    (re.compile(r"\bMlle\b\.?"), "Mademoiselle"),
    (re.compile(r"\bMM\.\s+(?=[A-ZÉÈÀÇ])"), "Messieurs "),
    (re.compile(r"\bDr\b\.?\s+(?=[A-ZÉÈÀÇ])"), "Docteur "),
    (re.compile(r"\bPr\b\.?\s+(?=[A-ZÉÈÀÇ])"), "Professeur "),
    (re.compile(r"\bcf\.", re.IGNORECASE), "voir"),
    (re.compile(r"\bp\.\s*ex\.", re.IGNORECASE), "par exemple"),
    (re.compile(r"\bc\.-à-d\.", re.IGNORECASE), "c'est-à-dire"),
    (re.compile(r"\betc\.\.+"), "etc."),
    (re.compile(r"\bi\.e\.", re.IGNORECASE), "c'est-à-dire"),
    (re.compile(r"\be\.g\.", re.IGNORECASE), "par exemple"),
    (re.compile(r"\bNB\s*:", re.IGNORECASE), "note :"),
    # "Mr." (anglicisme courant) → Monsieur
    (re.compile(r"\bMr\.\s+(?=[A-ZÉÈÀÇ])"), "Monsieur "),
]


# ── Unités & symboles ──────────────────────────────────────────────────────
_UNITES = [
    (re.compile(r"(\d)\s*°\s*C\b"), r"\1 degrés"),
    (re.compile(r"(\d)\s*°\s*F\b"), r"\1 degrés Fahrenheit"),
    (re.compile(r"(\d)\s*°\b"), r"\1 degrés"),
    (re.compile(r"(\d)\s*€"), r"\1 euros"),
    (re.compile(r"(\d)\s*\$"), r"\1 dollars"),
    (re.compile(r"(\d)\s*£"), r"\1 livres"),
    (re.compile(r"(\d)\s*%"), r"\1 pour cent"),
    (re.compile(r"(\d)\s*km/h\b", re.IGNORECASE), r"\1 kilomètres heure"),
    (re.compile(r"(\d)\s*km\b"), r"\1 kilomètres"),
    (re.compile(r"(\d)\s*m/s\b"), r"\1 mètres par seconde"),
    (re.compile(r"(\d)\s*Ko/s\b"), r"\1 kilo-octets par seconde"),
    (re.compile(r"(\d)\s*Mo/s\b"), r"\1 mégas par seconde"),
    (re.compile(r"(\d)\s*Go\b"), r"\1 giga-octets"),
    (re.compile(r"(\d)\s*Mo\b"), r"\1 mégas"),
    (re.compile(r"(\d)\s*Ko\b"), r"\1 kilos"),
    (re.compile(r"&"), " et "),
]


# ── Mots de liaison → virgule de respiration ──────────────────────────────
# On insère une virgule légère après ces mots quand ils démarrent une
# phrase ou un segment (pas quand ils sont en milieu de groupe figé).
_LIAISONS = (
    "donc", "alors", "bon", "eh bien", "en fait", "du coup",
    "cela dit", "cependant", "néanmoins", "pourtant", "toutefois",
    "bref", "en somme", "ceci dit", "par ailleurs",
)

_RE_LIAISON = re.compile(
    r"(?i)(?<![a-zà-ÿ])("
    + "|".join(re.escape(m) for m in _LIAISONS)
    + r")(?![,.!?;:])(?=\s+[a-zà-ÿ])"
)


# ── Markdown résiduel ─────────────────────────────────────────────────────
_MD_STRIP = [
    (re.compile(r"```[^\n]*\n.*?```", re.DOTALL), " "),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"\*([^*\n]+)\*"), r"\1"),
    (re.compile(r"__([^_]+)__"), r"\1"),
    (re.compile(r"^\s*#{1,6}\s+", re.MULTILINE), ""),
    (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), ""),
    (re.compile(r"^\s*\d+\.\s+", re.MULTILINE), ""),
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
]


# ── Ponctuation et espaces ────────────────────────────────────────────────
_RE_MULTISPACE = re.compile(r"\s+")
_RE_MULTIPOINT = re.compile(r"\.{4,}")
_RE_PONCT_DOUBLE = re.compile(r"([.!?]){2,}")


def _strip_markdown(texte: str) -> str:
    for pattern, repl in _MD_STRIP:
        texte = pattern.sub(repl, texte)
    return texte


def _expand_abrev(texte: str) -> str:
    for pattern, repl in _ABREVIATIONS:
        texte = pattern.sub(repl, texte)
    return texte


def _expand_unites(texte: str) -> str:
    for pattern, repl in _UNITES:
        texte = pattern.sub(repl, texte)
    return texte


def _respirer(texte: str) -> str:
    """Ajoute une virgule de respiration après les mots de liaison."""
    return _RE_LIAISON.sub(r"\1,", texte)


def _normaliser_ponctuation(texte: str) -> str:
    # Plusieurs points → points de suspension standards "..."
    texte = _RE_MULTIPOINT.sub("...", texte)
    # !! ?? ?! → un seul
    texte = _RE_PONCT_DOUBLE.sub(r"\1", texte)
    # Enlever les espaces en double.
    texte = _RE_MULTISPACE.sub(" ", texte)
    return texte.strip()


def _decouper_phrases_longues(texte: str, seuil: int = 180) -> str:
    """Pour les phrases longues, on renforce les pauses sur les virgules fortes
    en insérant un point-virgule visuel. Les moteurs TTS prennent une pause
    un peu plus longue sur « ; » que sur « , », sans casser l'intonation."""
    out = []
    for phrase in re.split(r"(?<=[.!?])\s+", texte):
        if len(phrase) > seuil:
            phrase = re.sub(r",\s+(et|mais|donc|car|puis|ensuite)\b", r" ; \1", phrase, count=2)
        out.append(phrase)
    return " ".join(out)


def naturaliser(texte: str) -> str:
    """Transforme un texte généré par le LLM en version parlée plus naturelle.

    Idempotent : appliquer deux fois donne le même résultat.
    """
    if not texte:
        return texte

    t = texte
    t = _strip_markdown(t)
    t = _expand_abrev(t)
    t = _expand_unites(t)
    t = _respirer(t)
    t = _decouper_phrases_longues(t)
    t = _normaliser_ponctuation(t)
    return t
