"""Moteur de proactivité de PHOEBUS.

PHOEBUS vérifie périodiquement un ensemble de règles et peut prendre la
parole de lui-même quand une condition est remplie (rappels, silence trop
long avec conversation ouverte, etc.). Chaque règle est une coroutine
indépendante pour que les nouvelles extensions soient faciles à brancher.

Règles disponibles :
  1. Silence ping          — "je vous écoute" après 40s dans une conversation
  2. Silence timeout       — ferme la conversation après 2 min
  3. Briefing matinal      — résumé journée + météo + agenda chaque matin
  4. Résumé quotidien LLM  — résume la journée écoulée à 3h du matin
  5. Alerte météo urgente  — prévient si orage/neige prévu dans l'heure
  6. Rappels calendrier    — annonce les RDV 15 min avant
"""
import asyncio
import time
from datetime import datetime

import PHOEBUS.state as state


_RULES = []

# Drapeaux anti-spam pour les règles ponctuelles
_alerte_meteo_ts: float = 0.0      # Dernière alerte météo envoyée
_rappel_rdv_cache: set = set()     # IDs des RDV déjà annoncés ce jour


def rule(fn):
    """Décorateur pour enregistrer une coroutine de règle proactive."""
    _RULES.append(fn)
    return fn


# ── Règle 1 : Silence ping ────────────────────────────────────────────────

@rule
async def _silence_ping(parler):
    """Après 40s de silence dans une conversation active, un 'je suis là'
    discret. Une seule fois par période de silence."""
    if not state.is_in_conversation():
        return
    s = state.seconds_since_user_activity()
    if s is None:
        return
    if 40 <= s < 90 and not state.silence_ping_sent:
        state.silence_ping_sent = True
        await parler("Je vous écoute toujours, Monsieur.")


# ── Règle 2 : Silence timeout ─────────────────────────────────────────────

@rule
async def _silence_timeout(parler):
    """Après 2 minutes sans rien, on clôt la conversation gracieusement."""
    if not state.is_in_conversation():
        return
    s = state.seconds_since_user_activity()
    if s is None:
        return
    if s > 120:
        state.end_conversation()


# ── Règle : Tick des timers/rappels persistants ───────────────────────────
@rule
async def _timers_tick(parler):
    """Vérifie les timers/rappels persistants et les prononce à échéance."""
    try:
        from PHOEBUS import timers as _timers
        await _timers.tick(parler)
    except Exception as e:
        print(f"[PROACTIVE] timers tick : {e}")


# ── Règle 3 : Briefing matinal ────────────────────────────────────────────

@rule
async def _briefing_matinal(parler):
    """Lance le briefing matinal si l'heure est venue et qu'on ne l'a pas encore fait."""
    if state.is_speaking or state.is_thinking:
        return
    try:
        from PHOEBUS.briefing import verifier_et_lancer_briefing
        await verifier_et_lancer_briefing(parler)
    except Exception as e:
        print(f"[PROACTIVE] Briefing erreur : {e}")


# ── Règle 4 : Résumé quotidien LLM (3h du matin) ─────────────────────────

@rule
async def _resume_quotidien(parler):
    """À 3h du matin, génère et stocke le résumé LLM de la journée écoulée."""
    if state.is_speaking or state.is_thinking:
        return
    try:
        from PHOEBUS.memory_timeline import resumer_journee_si_besoin
        resume = await resumer_journee_si_besoin()
        if resume:
            print(f"[PROACTIVE] Résumé quotidien effectué ({len(resume)} chars).")
    except Exception as e:
        print(f"[PROACTIVE] Résumé quotidien erreur : {e}")


# ── Règle 5 : Alerte météo urgente ───────────────────────────────────────

@rule
async def _alerte_meteo_urgente(parler):
    """Prévient proactivement en cas d'alerte météo sévère (orage, tempête)
    au moins une fois toutes les 4h si non déjà signalé."""
    global _alerte_meteo_ts
    if state.is_speaking or state.is_thinking:
        return
    now = time.time()
    # Max 1 alerte toutes les 4h
    if now - _alerte_meteo_ts < 4 * 3600:
        return
    try:
        from PHOEBUS.home import get_alertes_meteo
        alerte = await asyncio.to_thread(get_alertes_meteo)
        if alerte and "Aucune alerte" not in alerte and "orage" in alerte.lower() or (
            alerte and "Aucune alerte" not in alerte and "neige" in alerte.lower()
        ):
            _alerte_meteo_ts = now
            await parler(f"Floriace, une alerte météo mérite votre attention : {alerte}")
    except Exception as e:
        print(f"[PROACTIVE] Alerte météo erreur : {e}")


# ── Règle 6 : Rappels calendrier Google ──────────────────────────────────

@rule
async def _rappel_calendrier(parler):
    """Annonce les événements du calendrier 15 minutes avant leur début."""
    if state.is_speaking or state.is_thinking:
        return

    # Nettoyage du cache à minuit
    now = datetime.now()
    if now.hour == 0 and now.minute < 5:
        _rappel_rdv_cache.clear()

    try:
        from PHOEBUS.google_services import lister_evenements_prochains
        evenements = await asyncio.to_thread(lister_evenements_prochains, minutes_avant=15)
        for evt in (evenements or []):
            evt_id = evt.get("id", str(evt.get("debut", "")))
            if evt_id in _rappel_rdv_cache:
                continue
            _rappel_rdv_cache.add(evt_id)
            titre = evt.get("titre", "un événement")
            debut = evt.get("debut_str", "bientôt")
            lieu = evt.get("lieu", "")
            msg = f"Floriace, rappel : {titre} commence à {debut}."
            if lieu:
                msg += f" Lieu : {lieu}."
            await parler(msg)
    except AttributeError:
        pass  # lister_evenements_prochains n'existe pas encore — on ignore
    except Exception as e:
        print(f"[PROACTIVE] Rappel calendrier erreur : {e}")


# ── Boucle principale ─────────────────────────────────────────────────────

# ── Règle 7 : Indexation automatique du vault Obsidian ────────────────

_obsidian_index_ts: float = 0.0

@rule
async def _obsidian_auto_index(parler):
    """Indexe le vault Obsidian dans ChromaDB toutes les heures (en arrière-plan)."""
    global _obsidian_index_ts
    if state.is_speaking or state.is_thinking:
        return
    now = time.time()
    # Max une fois par heure
    if now - _obsidian_index_ts < 3600:
        return
    try:
        from PHOEBUS.obsidian import OBSIDIAN_ENABLED, index_vault_to_chroma
        if not OBSIDIAN_ENABLED:
            return
        _obsidian_index_ts = now
        result = await index_vault_to_chroma()
        indexed = result.get("indexed", 0)
        if indexed > 0:
            print(f"[PROACTIVE] Vault Obsidian indexé : {indexed} nouveaux chunks.")
    except Exception as e:
        print(f"[PROACTIVE] Indexation Obsidian erreur : {e}")


# ── Règle 8 : Synchronisation daily note Obsidian ─────────────────────

_daily_sync_done: str = ""

@rule
async def _obsidian_daily_sync(parler):
    """Crée la daily note du jour si elle n'existe pas encore (entre 7h et 8h)."""
    global _daily_sync_done
    if state.is_speaking or state.is_thinking:
        return
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    if _daily_sync_done == today_str:
        return
    if now.hour not in (7, 8):
        return
    try:
        from PHOEBUS.obsidian import OBSIDIAN_ENABLED, get_daily_note, write_note, _daily_path
        if not OBSIDIAN_ENABLED:
            return
        _daily_sync_done = today_str
        existing = await get_daily_note()
        if existing:
            return  # Déjà existante
        # Créer la daily note avec un template de base
        template = (
            f"---\n"
            f"date: {today_str}\n"
            f"tags: [daily]\n"
            f"source: phoebus\n"
            f"---\n\n"
            f"# {now.strftime('%A %d %B %Y')}\n\n"
            f"## Objectifs du jour\n\n"
            f"## Notes\n\n"
            f"## Réflexions\n\n"
        )
        path = _daily_path()
        await write_note(path, template)
        print(f"[PROACTIVE] Daily note créée : {path}")
    except Exception as e:
        print(f"[PROACTIVE] Daily note sync erreur : {e}")


# ── Boucle principale (suite) ─────────────────────────────────────────

async def loop(parler, tick_seconds: float = 5.0):
    """Boucle infinie à lancer en tâche asyncio au démarrage du serveur."""
    while True:
        for fn in list(_RULES):
            try:
                await fn(parler)
            except Exception as e:
                print(f"[PROACTIVE] Règle {getattr(fn, '__name__', '?')} erreur : {e}")
        await asyncio.sleep(tick_seconds)


def register_rule(fn):
    """Variante non-décorateur pour enregistrer une règle dynamiquement."""
    _RULES.append(fn)
    return fn
