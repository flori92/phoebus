# jarvis/briefing.py
"""
Briefing matinal automatique de JARVIS.

Chaque matin (heure configurable), Jarvis prend la parole de lui-même et
dresse un résumé personnalisé de la journée :
  - Météo du jour et alerte éventuelle
  - Événements du calendrier Google
  - Rappels importants de la mémoire timeline
  - Actualités (si SerpAPI configuré)
  - Résumé de la veille (depuis le RAG)
  - Musique de réveil Spotify (optionnel)

Variables d'environnement :
  JARVIS_BRIEFING_HOUR=8         → heure du briefing (défaut : 8h)
  JARVIS_BRIEFING_MUSIC=1        → lance une playlist de réveil (défaut : 0)
  JARVIS_BRIEFING_NEWS=1         → inclut les actualités (défaut : 1)
  JARVIS_BRIEFING_PLAYLIST=      → nom de la playlist Spotify de réveil
"""
import os
import asyncio
from datetime import datetime
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────

BRIEFING_HOUR      = int(os.getenv("JARVIS_BRIEFING_HOUR", "8"))
BRIEFING_MUSIC     = os.getenv("JARVIS_BRIEFING_MUSIC", "0").strip() == "1"
BRIEFING_NEWS      = os.getenv("JARVIS_BRIEFING_NEWS", "1").strip() == "1"
BRIEFING_PLAYLIST  = os.getenv("JARVIS_BRIEFING_PLAYLIST", "").strip()
BRIEFING_DONE_KEY  = "__briefing_done"

# ── État ──────────────────────────────────────────────────────────────────────

_briefing_done_today: Optional[str] = None   # Date (YYYY-MM-DD) du dernier briefing effectué


# ── Composants du briefing ────────────────────────────────────────────────────

async def _get_meteo_snippet() -> str:
    try:
        from jarvis.home import get_meteo_actuelle, get_alertes_meteo
        meteo = await asyncio.to_thread(get_meteo_actuelle)
        alertes = await asyncio.to_thread(get_alertes_meteo)
        if "Aucune alerte" not in alertes:
            return f"{meteo} {alertes}"
        return meteo
    except Exception as e:
        print(f"[BRIEFING] Météo erreur : {e}")
        return ""


async def _get_calendar_snippet() -> str:
    try:
        from jarvis.google_services import lister_evenements_calendar
        events = await asyncio.to_thread(lister_evenements_calendar)
        if events and "aucun" not in events.lower() and "pas d'événements" not in events.lower():
            return events
    except Exception as e:
        print(f"[BRIEFING] Calendrier erreur : {e}")
    return ""


async def _get_news_snippet() -> str:
    if not BRIEFING_NEWS:
        return ""
    try:
        from jarvis.home import recherche_web_serpapi
        news = await asyncio.to_thread(
            recherche_web_serpapi,
            "actualités France monde aujourd'hui"
        )
        if news and "clé SerpAPI" not in news and "erreur" not in news.lower():
            # Tronquer pour ne pas être trop long
            lignes = news.split("\n")[:3]
            return " ".join(lignes)
    except Exception as e:
        print(f"[BRIEFING] Actualités erreur : {e}")
    return ""


async def _get_memoire_snippet() -> str:
    try:
        from jarvis.memory_timeline import get_evenements_recents
        evts = [e for e in get_evenements_recents(20) if e.get("importance", 1) >= 2]
        if evts:
            # On ne reprend que les 2 plus récents importants
            derniers = evts[-2:]
            return " Par ailleurs, à retenir : " + " | ".join(
                e["contenu"][:80] for e in derniers
            )
    except Exception:
        pass
    return ""


async def _get_rag_snippet() -> str:
    """Cherche dans le RAG le résumé de la veille."""
    try:
        from jarvis.rag_memory import rechercher_souvenirs
        hier = (datetime.now().replace(hour=0)).strftime("%d/%m/%Y")
        souvenirs = await asyncio.to_thread(
            rechercher_souvenirs,
            f"résumé journée {hier}",
            2
        )
        if souvenirs and len(souvenirs) > 20:
            return f" Résumé d'hier : {souvenirs[:200]}..."
    except Exception:
        pass
    return ""


# ── Assemblage du briefing ────────────────────────────────────────────────────

async def generer_briefing() -> str:
    """Génère le texte complet du briefing matinal."""
    heure = datetime.now().hour
    salutation = (
        "Bonjour Floriace" if 5 <= heure < 12 else
        "Bonne après-midi Floriace" if 12 <= heure < 18 else
        "Bonsoir Floriace"
    )
    intro = f"{salutation}. Il est {datetime.now().strftime('%Hh%M')}. Voici votre briefing du jour."

    parties = [intro]

    # Météo
    meteo = await _get_meteo_snippet()
    if meteo:
        parties.append(meteo)

    # Calendrier
    calendar = await _get_calendar_snippet()
    if calendar:
        parties.append(f"Pour votre agenda aujourd'hui : {calendar}")

    # Actualités
    news = await _get_news_snippet()
    if news:
        parties.append(f"En bref dans l'actualité : {news}")

    # Mémoire timeline
    memoire = await _get_memoire_snippet()
    if memoire:
        parties.append(memoire)

    # Résumé RAG
    rag = await _get_rag_snippet()
    if rag:
        parties.append(rag)

    parties.append("Bonne journée Monsieur.")
    return " ".join(parties)


# ── Déclenchement proactif ────────────────────────────────────────────────────

async def verifier_et_lancer_briefing(parler_fn) -> bool:
    """À appeler périodiquement (depuis automation.py ou proactive.py).

    Renvoie True si un briefing a été lancé aujourd'hui.
    """
    global _briefing_done_today

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    if _briefing_done_today == today:
        return False

    if now.hour != BRIEFING_HOUR:
        return False

    if now.minute > 10:
        # On ne tente que dans les 10 premières minutes de l'heure
        return False

    _briefing_done_today = today
    print("[BRIEFING] Lancement du briefing matinal...")

    # Musique de réveil (optionnel, en arrière-plan)
    if BRIEFING_MUSIC:
        try:
            from jarvis.spotify import jouer as spotify_jouer
            playlist = BRIEFING_PLAYLIST or "morning jazz"
            asyncio.create_task(asyncio.to_thread(spotify_jouer, playlist))
            await asyncio.sleep(2)  # Laisser démarrer la musique
        except Exception as e:
            print(f"[BRIEFING] Spotify erreur : {e}")

    texte = await generer_briefing()
    await parler_fn(texte)

    # Stocker le briefing dans la timeline
    try:
        from jarvis.memory_timeline import enregistrer_evenement
        enregistrer_evenement("briefing", f"Briefing matinal du {today}", importance=2)
    except Exception:
        pass

    return True
