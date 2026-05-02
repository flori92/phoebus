import os
import time

from PHOEBUS.skills.registry import skill
from PHOEBUS.agent import orchestrer_agent_autonome
import PHOEBUS.state as state
import asyncio
from PHOEBUS.voice import parler


@skill(
    name="agent_natif",
    risk="high",
    help_text="Démarre l'agent autonome pour exécuter des scripts complexes sur l'ordinateur",
    describe=lambda d: f"lancer l'agent autonome pour accomplir la tâche : {d.get('instruction', 'Inconnue')[:40]}...",
)
async def skill_agent_natif(data: dict) -> str:
    instruction = data.get("instruction", "")
    if not instruction:
        return "Instruction manquante pour l'agent natif."

    await parler(f"J'initie l'agent autonome pour : {instruction}")

    async def _run_agent():
        res = await orchestrer_agent_autonome(instruction)
        await parler(f"Tâche autonome terminée : {res}")

    task = asyncio.create_task(_run_agent())
    state.register_background_task(task, label=f"agent_natif: {instruction[:60]}")


@skill(
    name="agent_planifie",
    risk="high",
    help_text="Planifie puis execute une tache complexe multi-etapes avec les outils disponibles",
    describe=lambda d: f"planifier la tache : {d.get('instruction', 'Inconnue')[:40]}...",
)
async def skill_agent_planifie(data: dict) -> str:
    instruction = data.get("instruction", "")
    if not instruction:
        return "Instruction manquante pour l'agent planifie."

    from PHOEBUS.planner import orchestrer_agent_planifie

    async def _run_planner():
        res = await orchestrer_agent_planifie(instruction, parler=parler)
        await parler(res)

    task = asyncio.create_task(_run_planner())
    state.register_background_task(task, label=f"agent_planifie: {instruction[:60]}")
    return "Je lance le planificateur autonome."


@skill(
    "demo",
    risk="low",
    help_text="Lance une démonstration visuelle spectaculaire de l'orbe",
    describe=lambda _: "Lancer une démonstration visuelle de mes capacités",
)
async def skill_demo(data: dict) -> str:
    await state.broadcast({"action": "demo"})
    return "Initialisation du protocole de démonstration. Observez bien, Floriace."


@skill(
    "launch_app",
    risk="medium",
    help_text="Lance une application ou un logiciel sur l'ordinateur",
    describe=lambda d: f"Ouvrir l'application : {d.get('name')}",
)
async def launch_app(data: dict):
    from PHOEBUS.utils import launch_app as _launch

    name = data.get("name")
    if not name:
        return "Quelle application voulez-vous ouvrir ?"

    ok = _launch(name)
    if ok:
        return f"J'ai lancé {name}, Monsieur."
    return f"Je n'ai pas pu trouver l'application {name} sur ce système."


@skill(
    "python_run",
    risk="medium",
    help_text="Execute du Python contraint pour les calculs, conversions et scripts deterministes",
    describe=lambda _: "Executer un calcul Python contraint",
)
async def python_run(data: dict):
    from PHOEBUS.code_runner import format_result_for_speech, run_python

    code = data.get("code", "")
    try:
        timeout_s = min(10.0, max(1.0, float(data.get("timeout_s", 5.0) or 5.0)))
    except (TypeError, ValueError):
        timeout_s = 5.0
    result = await run_python(code, timeout_s=timeout_s)
    return format_result_for_speech(result)


@skill(
    "brain_status",
    risk="low",
    help_text="Resume la sante du cerveau IA, des providers, des traces et des requetes recentes",
    describe=lambda _: "Lire l'etat du cerveau PHOEBUS",
)
async def brain_status(data: dict):
    from PHOEBUS.agent_runtime import recent_agent_runs
    from PHOEBUS.brain_router import router_status
    from PHOEBUS.llm_health import status as llm_status
    from PHOEBUS.observability import request_snapshot

    brain = router_status()
    now = time.time()
    available = set(brain.get("available") or [])
    metrics = brain.get("metrics") or {}
    provider_bits = []
    for provider in brain.get("order") or []:
        if provider not in available:
            continue
        item = metrics.get(provider, {}) if isinstance(metrics, dict) else {}
        cooldown = float(item.get("cooldown_until", 0) or 0)
        state_label = "cooldown" if cooldown > now else "pret"
        avg = item.get("avg_latency_ms")
        suffix = f", {avg} ms moyen" if avg else ""
        provider_bits.append(f"{provider}: {state_label}{suffix}")

    requests = request_snapshot(limit=30)
    runs = recent_agent_runs(limit=1)
    cooldowns = llm_status()
    last_run = runs[-1] if runs else None
    parts = [
        f"Mode cerveau: {brain.get('mode')}.",
        "Providers: " + (", ".join(provider_bits) if provider_bits else "aucun provider actif."),
        f"Requetes recentes: {requests.get('count', 0)}, p50 {requests.get('p50_ms', 0)} ms, p95 {requests.get('p95_ms', 0)} ms.",
    ]
    if cooldowns:
        cooldown_desc = ", ".join(
            f"{name} encore {info.get('remaining_s', 0)} s" for name, info in cooldowns.items()
        )
        parts.append("Cooldowns LLM: " + cooldown_desc + ".")
    if last_run:
        parts.append(
            f"Dernier agent: {last_run.get('status')} en {last_run.get('duration_ms')} ms."
        )
    return " ".join(parts)


@skill(
    "runtime_status",
    risk="low",
    help_text="Resume CPU, GPU, Tailscale et placement des taches PHOEBUS",
    describe=lambda _: "Lire le profil runtime PHOEBUS",
)
async def runtime_status(data: dict):
    from PHOEBUS.runtime_resources import runtime_snapshot

    snap = runtime_snapshot(force=bool(data.get("refresh", False)))
    profile = snap["profile"]
    policy = snap["task_policy"]
    accelerators = [
        f"{acc['name']} ({acc['kind']})"
        for acc in profile.get("accelerators", [])
        if acc.get("available")
    ]
    tailscale = profile.get("tailscale") or {}
    tailscale_msg = (
        f"Tailscale actif sur {tailscale.get('ip4')}"
        if tailscale.get("up")
        else "Tailscale non actif"
    )
    return (
        f"Runtime: {profile.get('cpu_brand')} avec {profile.get('cpu_count')} coeurs CPU. "
        f"Acceleration: {', '.join(accelerators) if accelerators else 'CPU uniquement'}. "
        f"STT sur {policy['stt']['device']} via {policy['stt']['backend']}; "
        f"vision sur {policy['vision']['device']}; LLM local sur {policy['local_llm']['device']}. "
        f"{tailscale_msg}."
    )


@skill(
    "tailscale_status",
    risk="low",
    help_text="Verifie l'etat Tailscale, l'IP tailnet et le nombre de pairs",
    describe=lambda _: "Verifier Tailscale",
)
async def tailscale_status(data: dict):
    from PHOEBUS.runtime_resources import detect_tailscale

    ts = detect_tailscale()
    if not ts.installed:
        return "Tailscale n'est pas installé sur cette machine."
    if not ts.up:
        return f"Tailscale est installé mais non connecté. {ts.error}".strip()
    tailnet = f" sur {ts.tailnet}" if ts.tailnet else ""
    peers = f"{ts.peers} appareil(s) visibles" if ts.peers else "aucun pair visible"
    return f"Tailscale est actif{tailnet}. IP: {ts.ip4}. {peers}."


@skill(
    "task_status",
    risk="low",
    help_text="Liste les taches de fond PHOEBUS en cours",
    describe=lambda _: "Lister les taches PHOEBUS actives",
)
async def task_status(data: dict):
    tasks = state.active_background_tasks()
    if not tasks:
        return "Aucune tâche de fond PHOEBUS n'est active."
    lines = []
    now = time.time()
    for tid, info in list(tasks.items())[:8]:
        age = int(now - float(info.get("started", now)))
        lines.append(f"{tid}: {info.get('label', 'tache')} depuis {age} secondes")
    suffix = "" if len(tasks) <= 8 else f", et {len(tasks) - 8} autre(s)"
    return "Tâches actives: " + "; ".join(lines) + suffix + "."


@skill(
    "task_cancel",
    risk="medium",
    help_text="Annule une tache de fond PHOEBUS par identifiant",
    describe=lambda d: f"Annuler la tache {d.get('id')}",
)
async def task_cancel(data: dict):
    tid = data.get("id")
    try:
        tid = int(tid)
    except (TypeError, ValueError):
        return "Identifiant de tâche invalide."
    return "Tâche annulée." if state.cancel_background_task(tid) else "Tâche introuvable."


@skill(
    "cache_status",
    risk="low",
    help_text="Affiche l'etat du cache vocal TTS",
    describe=lambda _: "Lire l'etat du cache PHOEBUS",
)
async def cache_status(data: dict):
    from PHOEBUS.response_cache import status as cache_status_snapshot

    snap = cache_status_snapshot()
    return (
        f"Cache vocal: {snap['entries']} fichier(s), {snap['size_mb']} Mo, "
        f"limite {snap['max_entries']} entrées."
    )


@skill(
    "cache_prune",
    risk="medium",
    help_text="Nettoie le cache vocal TTS selon la limite LRU",
    describe=lambda _: "Nettoyer le cache vocal PHOEBUS",
)
async def cache_prune(data: dict):
    from PHOEBUS.response_cache import CACHE_MAX_ENTRIES, prune

    try:
        max_entries = int(data.get("max_entries", CACHE_MAX_ENTRIES) or CACHE_MAX_ENTRIES)
    except (TypeError, ValueError):
        max_entries = CACHE_MAX_ENTRIES
    removed = prune(max_entries=max_entries)
    return f"Cache nettoyé. {removed} fichier(s) supprimé(s)."


@skill(
    "mode_local",
    risk="low",
    help_text="Active ou désactive le mode IA locale (Ollama)",
    describe=lambda d: f"Passer en mode IA {'locale' if d.get('etat') == 'on' else 'hybride'}",
)
async def mode_local(data: dict):
    etat = data.get("etat", "on") == "on"
    if etat:
        os.environ["PHOEBUS_BRAIN_MODE"] = "privacy"
        return "Mode local activé. J'utilise désormais exclusivement Ollama."
    else:
        os.environ["PHOEBUS_BRAIN_MODE"] = "smart"
        return "Mode hybride réactivé. Je retrouve toute ma puissance cloud."
