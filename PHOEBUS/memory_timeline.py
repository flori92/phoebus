# PHOEBUS/memory_timeline.py
"""
Mémoire long terme enrichie de PHOEBUS — Timeline + Résumés automatiques.

Trois couches complémentaires :
  1. Timeline JSON  — événements horodatés, persiste dans phoebus_timeline.json
  2. Résumés auto   — le LLM résume périodiquement les n derniers échanges en
                      une fiche "jour" stockée dans le RAG (ChromaDB).
  3. Profil évolutif — centres d'intérêt, personnes mentionnées, projets actifs.

Le module s'intègre via :
  - enregistrer_evenement(type, contenu)        → ajoute à la timeline
  - resumer_journee_si_besoin()                 → résumé LLM déclenché la nuit
  - enrichir_contexte_system_prompt(texte)      → snippet injectable dans le prompt
  - noter_personne(nom, contexte)               → profil des gens connus
"""
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from PHOEBUS.config import BASE_DIR, client, types, CHOSEN_MODEL

# ── Chemins ───────────────────────────────────────────────────────────────────

TIMELINE_FILE   = BASE_DIR / "phoebus_timeline.json"
PROFILE_FILE    = BASE_DIR / "phoebus_profile.json"

# ── Constantes ────────────────────────────────────────────────────────────────

MAX_TIMELINE_EVENTS = 500      # On garde les 500 derniers événements en mémoire vive
SUMMARY_HOUR        = 3        # Heure à laquelle le résumé quotidien est déclenché
SUMMARY_INTERVAL_H  = 22       # Ne pas résumer plus d'une fois toutes les 22h
MAX_EVENTS_PER_DAY_SUMMARY = 80  # Nb max d'événements résumés par le LLM

# ── Chargement / Sauvegarde ───────────────────────────────────────────────────

def _load_json(path: Path, default):
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save_json(path: Path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[TIMELINE] Sauvegarde échouée : {e}")


# ── Timeline ──────────────────────────────────────────────────────────────────

_timeline_cache: list | None = None
_last_summary_ts: float = 0.0


def _load_timeline() -> list:
    global _timeline_cache
    if _timeline_cache is not None:
        return _timeline_cache
    data = _load_json(TIMELINE_FILE, [])
    _timeline_cache = data[-MAX_TIMELINE_EVENTS:]
    return _timeline_cache


def _save_timeline(timeline: list):
    global _timeline_cache
    _timeline_cache = timeline
    _save_json(TIMELINE_FILE, timeline[-MAX_TIMELINE_EVENTS:])


def enregistrer_evenement(type_evt: str, contenu: str, importance: int = 1):
    """Ajoute un événement horodaté à la timeline.

    `type_evt` : 'conversation', 'action', 'domotique', 'rappel', 'systeme', etc.
    `importance` : 1 (banal) → 3 (important à retenir).
    """
    timeline = _load_timeline()
    evt = {
        "ts":         datetime.now().isoformat(timespec="seconds"),
        "type":       type_evt,
        "contenu":    contenu,
        "importance": importance,
    }
    timeline.append(evt)
    if len(timeline) > MAX_TIMELINE_EVENTS:
        timeline = timeline[-MAX_TIMELINE_EVENTS:]
    _save_timeline(timeline)

    # Stocker automatiquement les événements importants dans le RAG
    if importance >= 2:
        try:
            from PHOEBUS.rag_memory import stocker_souvenir
            stocker_souvenir(contenu, source=type_evt, importance=importance)
        except Exception:
            pass


def get_evenements_recents(n: int = 20, type_evt: str | None = None) -> list:
    """Renvoie les n derniers événements, filtrés optionnellement par type."""
    timeline = _load_timeline()
    if type_evt:
        timeline = [e for e in timeline if e.get("type") == type_evt]
    return timeline[-n:]


def get_evenements_jour(date: datetime | None = None) -> list:
    """Renvoie tous les événements du jour donné (ou aujourd'hui)."""
    date = date or datetime.now()
    prefix = date.strftime("%Y-%m-%d")
    return [e for e in _load_timeline() if e.get("ts", "").startswith(prefix)]


# ── Résumé LLM automatique ────────────────────────────────────────────────────

_last_summary_check: float = 0.0


async def resumer_journee_si_besoin() -> Optional[str]:
    """Lance un résumé LLM de la journée précédente si :
    - Il est entre SUMMARY_HOUR h et SUMMARY_HOUR+1 h
    - Le dernier résumé date de plus de SUMMARY_INTERVAL_H heures.

    Stocke le résumé dans le RAG et renvoie le texte (ou None).
    """
    global _last_summary_ts, _last_summary_check

    now = time.time()
    # Ne vérifier qu'une fois toutes les 10 minutes pour ne pas spammer
    if now - _last_summary_check < 600:
        return None
    _last_summary_check = now

    heure = datetime.now().hour
    if heure != SUMMARY_HOUR:
        return None
    if now - _last_summary_ts < SUMMARY_INTERVAL_H * 3600:
        return None
    if not client or not types:
        return None

    _last_summary_ts = now

    # Récupérer les événements d'hier
    hier = datetime.now() - timedelta(days=1)
    evts = get_evenements_jour(hier)
    if len(evts) < 3:
        return None

    # Formater pour le LLM
    evts_str = "\n".join(
        f"[{e['ts'][11:16]}] ({e['type']}) {e['contenu']}"
        for e in evts[-MAX_EVENTS_PER_DAY_SUMMARY:]
    )
    prompt = (
        f"Voici la journée de Floriace du {hier.strftime('%A %d %B %Y')} :\n\n"
        f"{evts_str}\n\n"
        "Résume cette journée en 3-5 phrases concises : "
        "ce qui a été fait, discuté, les actions importantes, l'humeur perçue. "
        "Commence directement, pas de titre. En français."
    )

    try:
        import asyncio
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.5),
        )
        resume = (response.text or "").strip()
        if resume:
            from PHOEBUS.rag_memory import stocker_souvenir
            stocker_souvenir(
                f"Résumé du {hier.strftime('%d/%m/%Y')} : {resume}",
                source="resume_quotidien",
                importance=3,
            )
            print(f"[TIMELINE] Résumé quotidien stocké ({len(resume)} chars).")
            return resume
    except Exception as e:
        print(f"[TIMELINE] Erreur résumé LLM : {e}")

    return None


# ── Profil des personnes connues ──────────────────────────────────────────────

def _load_profile() -> dict:
    return _load_json(PROFILE_FILE, {"personnes": {}, "projets": {}, "preferences": {}})


def _save_profile(profile: dict):
    _save_json(PROFILE_FILE, profile)


def noter_personne(nom: str, contexte: str, relation: str = ""):
    """Enregistre ou enrichit la fiche d'une personne mentionnée."""
    nom = nom.strip().title()
    profile = _load_profile()
    personnes = profile.setdefault("personnes", {})
    fiche = personnes.setdefault(nom, {"mentions": 0, "contextes": [], "relation": relation})
    fiche["mentions"] = fiche.get("mentions", 0) + 1
    fiche["dernier_contact"] = datetime.now().strftime("%Y-%m-%d")
    if relation:
        fiche["relation"] = relation
    contextes = fiche.setdefault("contextes", [])
    if contexte and contexte not in contextes:
        contextes.append(contexte)
    if len(contextes) > 10:
        fiche["contextes"] = contextes[-10:]
    _save_profile(profile)


def noter_projet(nom: str, description: str, statut: str = "actif"):
    """Enregistre ou met à jour un projet de Floriace."""
    nom = nom.strip()
    profile = _load_profile()
    projets = profile.setdefault("projets", {})
    projet = projets.setdefault(nom, {"statut": statut, "notes": []})
    projet["statut"] = statut
    projet["derniere_mention"] = datetime.now().strftime("%Y-%m-%d")
    notes = projet.setdefault("notes", [])
    if description and description not in notes:
        notes.append(f"[{datetime.now().strftime('%d/%m')}] {description}")
    if len(notes) > 15:
        projet["notes"] = notes[-15:]
    _save_profile(profile)


def noter_preference(cle: str, valeur: str):
    """Apprend une préférence de Floriace (ex: 'café': 'sans sucre')."""
    profile = _load_profile()
    profile.setdefault("preferences", {})[cle.lower()] = {
        "valeur": valeur,
        "ts": datetime.now().strftime("%Y-%m-%d"),
    }
    _save_profile(profile)


# ── Enrichissement du system prompt ──────────────────────────────────────────

def enrichir_contexte_system_prompt(texte_utilisateur: str = "") -> str:
    """Génère un bloc de contexte à injecter dans le system prompt.

    Contient :
    - Les 5 derniers événements importants
    - Les personnes et projets actifs pertinents
    - Un résumé du profil Floriace
    """
    lignes = []

    # Événements récents importants
    evts = [e for e in get_evenements_recents(30) if e.get("importance", 1) >= 2]
    if evts:
        lignes.append("MÉMOIRE RÉCENTE (événements importants) :")
        for e in evts[-5:]:
            lignes.append(f"  [{e['ts'][:10]}] {e['contenu']}")

    # Profil personnes & projets
    profile = _load_profile()
    personnes = profile.get("personnes", {})
    if personnes:
        top_personnes = sorted(personnes.items(), key=lambda x: -x[1].get("mentions", 0))[:5]
        noms = [f"{n} ({d.get('relation', '?')})" for n, d in top_personnes]
        lignes.append(f"PERSONNES CONNUES : {', '.join(noms)}")

    projets = profile.get("projets", {})
    actifs = [(n, p) for n, p in projets.items() if p.get("statut") == "actif"]
    if actifs:
        lignes.append("PROJETS ACTIFS DE FLORIACE :")
        for nom, proj in actifs[:4]:
            derniere_note = (proj.get("notes") or [""])[-1]
            lignes.append(f"  - {nom} : {derniere_note}")

    prefs = profile.get("preferences", {})
    if prefs:
        pref_str = ", ".join(f"{k}={v['valeur']}" for k, v in list(prefs.items())[:6])
        lignes.append(f"PRÉFÉRENCES APPRISES : {pref_str}")

    # Notes personnelles pertinentes (Obsidian + SiYuan) si le sujet correspond
    if texte_utilisateur:
        try:
            from PHOEBUS.knowledge_vault import is_enabled, search_semantic
            if is_enabled():
                import asyncio
                try:
                    # On tente de récupérer la boucle actuelle, sinon on en crée une
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    if loop.is_running():
                        # Si la boucle tourne déjà (v2), on ne peut pas faire run_until_complete
                        # Dans ce cas, on skip ou on utilise une astuce. 
                        # Pour la cohérence v2, search_semantic devrait être appelé en amont.
                        vault_hits = [] 
                    else:
                        vault_hits = loop.run_until_complete(
                            search_semantic(texte_utilisateur, n_results=2)
                        )
                except Exception as e:
                    vault_hits = []
                if vault_hits:
                    lignes.append("NOTES PERSONNELLES PERTINENTES :")
                    for hit in vault_hits[:2]:
                        f = hit.get("file", "?")
                        src = hit.get("source", "notes")
                        snippet = hit.get("text", "")[:200].replace("\n", " ")
                        lignes.append(f"  [{src}: {f}] {snippet}")
        except Exception:
            pass

    return "\n".join(lignes) if lignes else ""
