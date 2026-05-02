# PHOEBUS/skills/obsidian_skills.py
"""Skills vocales/textuelles Notes pour PHOEBUS.

Utilise la façade unifiée `knowledge_vault` qui route vers
SiYuan, Obsidian API, ou Obsidian filesystem selon la configuration.

Commandes naturelles :
  - "note : <contenu>"               → capture rapide
  - "ajoute à ma daily : <contenu>"  → append daily note
  - "cherche dans mes notes <query>" → recherche textuelle + sémantique
  - "lis ma note sur <sujet>"        → lecture + résumé
  - "ouvre mes notes sur <sujet>"    → ouvre dans Obsidian
  - "résume mes notes de la semaine" → agrège les daily notes récentes
  - "quels sont mes TODOs ?"         → liste les tâches incomplètes
  - "indexe mes notes"               → force la ré-indexation ChromaDB
"""
from PHOEBUS.skills.registry import skill
import asyncio


def _vault():
    """Import tardif de la façade unifiée."""
    from PHOEBUS import knowledge_vault
    return knowledge_vault


# ── Capture rapide ──────────────────────────────────────────────────────────

@skill(
    "obsidian_capture",
    risk="low",
    help_text="Capture une note rapide (SiYuan ou Obsidian)",
    describe=lambda d: f"Créer la note : {d.get('title', d.get('content', '')[:40])}",
)
async def skill_obsidian_capture(data: dict):
    v = _vault()
    if not v.is_enabled():
        return "Aucun backend notes configuré. Active OBSIDIAN_ENABLED=1 et/ou SIYUAN_ENABLED=1 dans le .env."
    content = data.get("content", "").strip()
    if not content:
        return "Que dois-je noter ?"
    title = data.get("title", "").strip()
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    folder = data.get("folder", "").strip()
    path = await v.capture_note(content, title=title, tags=tags, folder=folder)
    backend = v.backends_summary()
    return f"Note créée via {backend} : {path}"


# ── Daily Note ──────────────────────────────────────────────────────────────

@skill(
    "obsidian_daily_append",
    risk="low",
    help_text="Ajoute du contenu à la daily note du jour",
    describe=lambda d: f"Ajouter à la daily note : {d.get('content', '')[:40]}",
)
async def skill_obsidian_daily_append(data: dict):
    v = _vault()
    if not v.is_enabled():
        return "Aucun backend notes configuré."
    content = data.get("content", "").strip()
    if not content:
        return "Que dois-je ajouter à la daily note ?"
    from datetime import datetime
    now = datetime.now()
    entry = f"\n- **{now.strftime('%H:%M')}** — {content}"
    ok = await v.append_daily(entry)
    if ok:
        return f"Ajouté à la daily note du {now.strftime('%d/%m/%Y')}."
    return "Impossible d'ajouter à la daily note. Vérifie la configuration."


# ── Recherche ───────────────────────────────────────────────────────────────

@skill(
    "obsidian_search",
    risk="low",
    help_text="Recherche dans les notes (textuelle + sémantique, multi-backend)",
    describe=lambda d: f"Chercher dans les notes : {d.get('query', '')}",
)
async def skill_obsidian_search(data: dict):
    v = _vault()
    if not v.is_enabled():
        return "Aucun backend notes configuré."
    query = data.get("query", "").strip()
    if not query:
        return "Que dois-je chercher dans tes notes ?"

    # Lancer les deux recherches en parallèle
    text_results, semantic_results = await asyncio.gather(
        v.search_text(query),
        v.search_semantic(query, n_results=5),
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
            src = r.get("source", "?")
            snippet = r["text"][:120].replace("\n", " ")
            lines.append(f"  - [{src}] **{f}** (score: {r['score']}) : {snippet}…")

    # Résultats textuels
    if text_results:
        lines.append("**Résultats textuels :**")
        for r in text_results[:5]:
            fn = r.get("filename", "?")
            backend = r.get("backend", "?")
            ctx = ""
            matches = r.get("matches", [])
            if matches:
                ctx = matches[0].get("context", "")[:100].replace("\n", " ")
            lines.append(f"  - [{backend}] **{fn}** : {ctx}")

    if not lines:
        return f"Aucun résultat pour « {query} » dans les notes."
    return "\n".join(lines)


# ── Lecture d'une note ──────────────────────────────────────────────────────

@skill(
    "obsidian_read",
    risk="low",
    help_text="Lit et résume une note",
    describe=lambda d: f"Lire la note : {d.get('path', d.get('query', ''))}",
)
async def skill_obsidian_read(data: dict):
    v = _vault()
    if not v.is_enabled():
        return "Aucun backend notes configuré."

    path = data.get("path", "").strip()
    query = data.get("query", "").strip()

    # Si pas de chemin exact, chercher par nom
    if not path and query:
        results = await v.search_text(query)
        if results:
            path = results[0].get("filename", "")
        else:
            sem = await v.search_semantic(query, n_results=1)
            if sem:
                path = sem[0].get("file", "")

    if not path:
        return f"Je n'ai pas trouvé de note correspondant à « {query or '?'} »."

    content = await v.read_note(path)
    if not content:
        return f"Impossible de lire la note : {path}"

    if len(content) < 800:
        return f"**{path}** :\n\n{content}"

    return f"**{path}** ({len(content)} caractères) :\n\n{content[:1500]}…\n\n*(Note tronquée — demande un résumé pour la synthèse complète)*"


# ── Ouvrir dans l'app ───────────────────────────────────────────────────────

@skill(
    "obsidian_open",
    risk="low",
    help_text="Ouvre une note dans l'interface de l'app (Obsidian)",
    describe=lambda d: f"Ouvrir la note : {d.get('path', d.get('query', ''))}",
)
async def skill_obsidian_open(data: dict):
    v = _vault()
    if not v.is_enabled():
        return "Aucun backend notes configuré."

    path = data.get("path", "").strip()
    query = data.get("query", "").strip()

    if not path and query:
        results = await v.search_text(query)
        if results:
            path = results[0].get("filename", "")

    if not path:
        return f"Je n'ai pas trouvé de note pour « {query or '?'} »."

    ok = await v.open_in_app(path)
    if ok:
        return f"J'ai ouvert **{path}** dans l'application."
    return f"Impossible d'ouvrir {path}."


# ── TODOs ───────────────────────────────────────────────────────────────────

@skill(
    "obsidian_todos",
    risk="low",
    help_text="Liste les tâches incomplètes dans les notes",
    describe=lambda d: "Chercher les TODOs dans les notes",
)
async def skill_obsidian_todos(data: dict):
    v = _vault()
    if not v.is_enabled():
        return "Aucun backend notes configuré."

    todos = await v.find_todos(limit=20)
    if not todos:
        return "Aucune tâche incomplète trouvée."

    lines = [f"**{len(todos)} tâche(s) incomplète(s) :**"]
    for t in todos:
        backend = t.get("backend", "?")
        lines.append(f"  - [ ] {t['text']}  *({backend}: {t['file']})*")
    return "\n".join(lines)


# ── Résumé hebdomadaire ─────────────────────────────────────────────────────

@skill(
    "obsidian_weekly_summary",
    risk="low",
    help_text="Résume les daily notes de la semaine",
    describe=lambda d: "Résumer les notes de la semaine",
)
async def skill_obsidian_weekly_summary(data: dict):
    v = _vault()
    if not v.is_enabled():
        return "Aucun backend notes configuré."

    from datetime import datetime, timedelta
    now = datetime.now()
    contents = []
    for i in range(7):
        date = now - timedelta(days=i)
        note = await v.get_daily_note(date)
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
    help_text="Force l'indexation des notes dans la mémoire vectorielle",
    describe=lambda d: "Indexer les notes dans ChromaDB",
)
async def skill_obsidian_index(data: dict):
    v = _vault()
    if not v.is_enabled():
        return "Aucun backend notes configuré."

    result = await v.index_all(force=True)
    total = result.get("total", {})
    parts = []
    for backend, r in result.items():
        if backend == "total":
            continue
        parts.append(f"**{backend}** : {r.get('indexed', 0)} chunks")
    detail = ", ".join(parts) if parts else "aucun"
    return (
        f"Indexation terminée : {total.get('indexed', 0)} chunks au total "
        f"({detail}), {total.get('errors', 0)} erreurs."
    )


# ── Aliases de capture rapide (fast-path intent) ──────────────────────────

@skill(
    "note_capture",
    risk="low",
    help_text="Capture vocale rapide d'une note",
    describe=lambda d: f"Capturer : {d.get('content', '')[:40]}",
)
async def skill_note_capture(data: dict):
    """Alias rapide de obsidian_capture pour le fast-path intent."""
    return await skill_obsidian_capture(data)


@skill(
    "note_search",
    risk="low",
    help_text="Recherche rapide dans les notes",
    describe=lambda d: f"Chercher : {d.get('query', '')}",
)
async def skill_note_search(data: dict):
    """Alias rapide de obsidian_search pour le fast-path intent."""
    return await skill_obsidian_search(data)

