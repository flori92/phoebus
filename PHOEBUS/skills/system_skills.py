from PHOEBUS.skills.registry import skill
from PHOEBUS.agent import orchestrer_agent_autonome
import PHOEBUS.state as state
import asyncio
from PHOEBUS.voice import parler

@skill(
    name="agent_natif",
    risk="high",
    help_text="Démarre l'agent autonome pour exécuter des scripts complexes sur l'ordinateur",
    describe=lambda d: f"lancer l'agent autonome pour accomplir la tâche : {d.get('instruction', 'Inconnue')[:40]}..."
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
    return "Agent autonome lancé en arrière-plan."
