# PHOEBUS/skills/obsidian_skills.py
"""Skills vocales/textuelles Obsidian pour PHOEBUS.

Commandes naturelles :
  - "note : <contenu>"               → capture rapide dans Inbox
  - "ajoute à ma daily : <contenu>"  → append daily note
  - "cherche dans mes notes <query>" → recherche textuelle + sémantique
  - "lis ma note sur <sujet>"        → lecture + résumé LLM
  - "ouvre mes notes sur <sujet>"    → ouvre dans Obsidian
  - "résume mes notes de la semaine" → agrège les daily notes récentes
  - "quels sont mes TODOs ?"         → liste les tâches incomplètes
  - "indexe mes notes"               → force la ré-indexation ChromaDB
"""
from PHOEBUS.skills.registry import skill
import asyncio


def _obsidian():
    """Import tardif pour ne pas bloquer le boot si Obsidian n'est pas configuré."""
    from PHOEBUS import obsidian
    return obsidian


# ── Capture rapide ──────────────────────────────────────────────────────────

@skill(
    "obsidian_capture",
    risk="low",
    help_text="Capture une note rapide dans Obsidian (Inbox)",
    describe=lambda d: f"Créer la note : {d.get('title', d.get('content', '')[:40])}",
)
async def skill_obsidian_capture(data: dict):
    obs = _obsidian()
    if not obs.OBSIDIAN_ENABLED:
        return "L'intégration Obsidian n'est pas activée. Configure OBSIDIAN_ENABLED=1 dans le .env."
    content = data.get("content", "").strip()
    if not content:
        return "Que dois-je noter ?"
    title = data.get("title", "").strip()
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    folder = data.get("folder", "").strip()
    path = await obs.capture_note(content, title=title, tags=tags, folder=folder)
    return f"Note créée dans Obsidian : {path}"


# ── Daily Note ──────────────────────────────────────────────────────────────

@skill(
    "obsidian_daily_append",
    risk="low",
    help_text="Ajoute du contenu à la daily note du jour dans Obsidian",
    describe=lambda d: f"Ajouter à la daily note : {d.get('content', '')[:40]}",
)
async def skill_obsidian_daily_append(data: dict):
    obs = _obsidian()
    if not obs.OBSIDIAN_ENABLED:
        return "L'intégration Obsidian n'est pas activée."
    content = data.get("content", "").strip()
    if not content:
        return "Que dois-je ajouter à la daily note ?"
    from datetime import datetime
    now = datetime.now()
    entry = f"\n- **{now.strftime('%H:%M')}** — {content}"
    ok = await obs.append_daily(entry)
    if ok:
        return f"Ajouté à la daily note du {now.strftime('%d/%m/%Y')}."
    return "Impossible d'ajouter à la daily note. Vérifie la configuration Obsidian."


# ── Recherche ───────────────────────────────────────────────────────────────

@skill(
    "obsidian_search",
    risk="low",
    help_text="Recherche dans les notes Obsidian (textuelle + sémantique)",
    describe=lambda d: f"Chercher dans les notes : {d.get('query', '')}",
)
async def skill_obsidian_search(data: dict):
    obs = _obsidian()
    if not obs.OBSIDIAN_ENABLED:
        return "L'intégration Obsidian n'est pas activée."
    query = data.get("query", "").strip()
    if not query:
        return "Que dois-je chercher dans tes notes ?"

    # Lancer les deux recherches en parallèle
    text_results, semantic_results = await asyncio.gather(
        obs.search_text(query),
        obs.search_vault_semantic(query, n_results=5),
    )

    lines = []

    # Résultats sémantiques (meilleure pertinence)
    if semantic_results:
        lines.append("**Résultats pertinents (recherche sémantique) :**")
        seen = set()
        for r in semantic_results[:5]:
            f = r["file"]
            if f in seen:
                continue
            seen.add(f)
            snippet = r["text"][:120].replace("\n", " ")
            lines.append(f"  - **{f}** (score: {r['score']}) : {snippet}…")

    # Résultats textuels
    if text_results:
        lines.append("**Résultats textuels :**")
        for r in text_results[:5]:
            fn = r.get("filename", "?")
            ctx = ""
            matches = r.get("matches", [])
            if matches:
                ctx = matches[0].get("context", "")[:100].replace("\n", " ")
            lines.append(f"  - **{fn}** : {ctx}")

    if not lines:
        return f"Aucun résultat pour « {query} » dans le vault Obsidian."
    return "\n".join(lines)


# ── Lecture d'une note ──────────────────────────────────────────────────────

@skill(
    "obsidian_read",
    risk="low",
    help_text="Lit et résume une note Obsidian",
    describe=lambda d: f"Lire la note : {d.get('path', d.get('query', ''))}",
)
async def skill_obsidian_read(data: dict):
    obs = _obsidian()
    if not obs.OBSIDIAN_ENABLED:
        return "L'intégration Obsidian n'est pas activée."

    path = data.get("path", "").strip()
    query = data.get("query", "").strip()

    # Si pas de chemin exact, chercher par nom
    if not path and query:
        results = await obs.search_text(query)
        if results:
            path = results[0].get("filename", "")
        else:
            # Essayer recherche sémantique
            sem = await obs.search_vault_semantic(query, n_results=1)
            if sem:
                path = sem[0].get("file", "")

    if not path:
        return f"Je n'ai pas trouvé de note correspondant à « {query or '?'} »."

    content = await obs.read_note(path)
    if not content:
        return f"Impossible de lire la note : {path}"

    # Si la note est courte, la retourner directement
    if len(content) < 800:
        return f"**{path}** :\n\n{content}"

    # Sinon résumer via le LLM
    return f"**{path}** ({len(content)} caractères) :\n\n{content[:1500]}…\n\n*(Note tronquée à 1500 chars — demande un résumé si tu veux la synthèse)*"


# ── Ouvrir dans Obsidian ────────────────────────────────────────────────────

@skill(
    "obsidian_open",
    risk="low",
    help_text="Ouvre une note dans l'interface Obsidian",
    describe=lambda d: f"Ouvrir dans Obsidian : {d.get('path', d.get('query', ''))}",
)
async def skill_obsidian_open(data: dict):
    obs = _obsidian()
    if not obs.OBSIDIAN_ENABLED:
        return "L'intégration Obsidian n'est pas activée."

    path = data.get("path", "").strip()
    query = data.get("query", "").strip()

    if not path and query:
        results = await obs.search_text(query)
        if results:
            path = results[0].get("filename", "")

    if not path:
        return f"Je n'ai pas trouvé de note pour « {query or '?'} »."

    ok = await obs.open_note_in_obsidian(path)
    if ok:
        return f"J'ai ouvert **{path}** dans Obsidian."
    return f"Impossible d'ouvrir {path} dans Obsidian."


# ── TODOs ───────────────────────────────────────────────────────────────────

@skill(
    "obsidian_todos",
    risk="low",
    help_text="Liste les tâches incomplètes dans les notes Obsidian",
    describe=lambda d: "Chercher les TODOs dans les notes",
)
async def skill_obsidian_todos(data: dict):
    obs = _obsidian()
    if not obs.OBSIDIAN_ENABLED:
        return "L'intégration Obsidian n'est pas activée."

    todos = await obs.find_todos(limit=20)
    if not todos:
        return "Aucune tâche incomplète trouvée dans le vault Obsidian."

    lines = [f"**{len(todos)} tâche(s) incomplète(s) :**"]
    for t in todos:
        lines.append(f"  - [ ] {t['text']}  *(dans {t['file']})*")
    return "\n".join(lines)


# ── Résumé hebdomadaire ─────────────────────────────────────────────────────

@skill(
    "obsidian_weekly_summary",
    risk="low",
    help_text="Résume les daily notes de la semaine",
    describe=lambda d: "Résumer les notes de la semaine",
)
async def skill_obsidian_weekly_summary(data: dict):
    obs = _obsidian()
    if not obs.OBSIDIAN_ENABLED:
        return "L'intégration Obsidian n'est pas activée."

    from datetime import datetime, timedelta
    now = datetime.now()
    contents = []
    for i in range(7):
        date = now - timedelta(days=i)
        note = await obs.get_daily_note(date)
        if note and note.strip():
            contents.append(f"### {date.strftime('%A %d/%m')} :\n{note[:500]}")

    if not contents:
        return "Aucune daily note trouvée pour cette semaine."

    summary = "\n\n".join(contents)
    return f"**Résumé des daily notes de la semaine :**\n\n{summary}"


# ── Indexation manuelle ─────────────────────────────────────────────────────

@skill(
    "obsidian_index",
    risk="low",
    help_text="Force l'indexation du vault Obsidian dans la mémoire vectorielle",
    describe=lambda d: "Indexer les notes Obsidian dans ChromaDB",
)
async def skill_obsidian_index(data: dict):
    obs = _obsidian()
    if not obs.OBSIDIAN_ENABLED:
        return "L'intégration Obsidian n'est pas activée."

    result = await obs.index_vault_to_chroma(force=True)
    return (
        f"Indexation terminée : {result['indexed']} chunks indexés, "
        f"{result['skipped']} ignorés, {result['errors']} erreurs "
        f"en {result.get('duration_s', '?')}s."
    )
