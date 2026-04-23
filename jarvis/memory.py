# jarvis/memory.py
"""Mémoire persistante de JARVIS — stockage JSON local."""
import json
import os
import time

from jarvis.config import MEMOIRE_FILE


def charger_memoire():
    if os.path.exists(MEMOIRE_FILE):
        try:
            with open(MEMOIRE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def sauvegarder_memoire(memoire):
    try:
        with open(MEMOIRE_FILE, "w", encoding="utf-8") as f:
            json.dump(memoire, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erreur sauvegarde memoire : {e}")


def ajouter_memoire(cle, valeur):
    memoire      = charger_memoire()
    memoire[cle] = {"valeur": valeur, "timestamp": time.strftime("%d/%m/%Y %H:%M")}
    sauvegarder_memoire(memoire)


def supprimer_memoire(cle):
    memoire = charger_memoire()
    if cle in memoire:
        del memoire[cle]
        sauvegarder_memoire(memoire)
        return True
    return False


def construire_contexte_memoire():
    memoire = charger_memoire()
    if not memoire:
        return ""
    lignes = ["MEMOIRE PERSISTANTE :"]
    for cle, data in memoire.items():
        if cle == _PROFILE_KEY or not isinstance(data, dict) or "valeur" not in data:
            continue
        lignes.append(f"  - {cle} : {data['valeur']} (note le {data['timestamp']})")
    return "\n".join(lignes) if len(lignes) > 1 else ""


# ── Profil apprenant ────────────────────────────────────────────────────────
# Petit dictionnaire de compteurs appris automatiquement :
#   - thèmes discutés souvent,
#   - registre préféré (tu / vous détecté dans les derniers tours),
#   - horaires d'interaction,
#   - pièces sollicitées en domotique.
# Stocké dans le même fichier sous la clé spéciale "_profile".

_PROFILE_KEY = "_profile"


def _load_profile():
    m = charger_memoire()
    return m.get(_PROFILE_KEY, {}) or {}


def _save_profile(profile):
    m = charger_memoire()
    m[_PROFILE_KEY] = profile
    sauvegarder_memoire(m)


def apprendre_signal(cle, valeur=1):
    """Incrémente un compteur (pièce utilisée, thème évoqué, registre...)."""
    profile = _load_profile()
    compteurs = profile.setdefault("compteurs", {})
    compteurs[cle] = compteurs.get(cle, 0) + valeur
    profile["dernier_update"] = time.strftime("%d/%m/%Y %H:%M")
    _save_profile(profile)


def noter_registre(tu_ou_vous: str):
    """`tu_ou_vous` ∈ {'tu','vous'}. Bascule lissée du registre perçu."""
    if tu_ou_vous not in ("tu", "vous"):
        return
    profile = _load_profile()
    reg = profile.setdefault("registre", {"tu": 0, "vous": 0})
    reg[tu_ou_vous] = reg.get(tu_ou_vous, 0) + 1
    _save_profile(profile)


def resumer_profil():
    """Petit résumé texte injectable dans le system prompt."""
    profile = _load_profile()
    if not profile:
        return ""
    lignes = ["PROFIL APPRIS DE FLORIACE (mis à jour automatiquement) :"]

    reg = profile.get("registre") or {}
    if reg:
        if reg.get("tu", 0) > reg.get("vous", 0) * 1.5:
            lignes.append("  - Registre : il te tutoie habituellement, réponds-lui sur le même ton.")
        elif reg.get("vous", 0) > reg.get("tu", 0) * 1.2:
            lignes.append("  - Registre : il te vouvoie. Reste au vouvoiement.")

    comp = profile.get("compteurs") or {}
    if comp:
        top = sorted(comp.items(), key=lambda kv: -kv[1])[:5]
        top_fmt = ", ".join(f"{k}" for k, _ in top if not k.startswith("_"))
        if top_fmt:
            lignes.append(f"  - Centres d'intérêt récurrents : {top_fmt}.")

    return "\n".join(lignes) if len(lignes) > 1 else ""


def detecter_registre(texte: str):
    """Détecte 'tu' ou 'vous' dans le texte utilisateur, sinon None."""
    t = (texte or "").lower()
    tokens = set(t.split())
    if any(m in tokens for m in ("tu", "t'es", "t'as", "peux-tu", "peux", "dis-moi")) and "vous" not in tokens:
        return "tu"
    if any(m in t for m in ("vous ", "pouvez", "dites-moi")):
        return "vous"
    return None
