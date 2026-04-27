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
@skill(
    "demo",
    risk="low",
    help_text="Lance une démonstration visuelle spectaculaire de l'orbe",
    describe=lambda _: "Lancer une démonstration visuelle de mes capacités"
)
async def skill_demo(data: dict) -> str:
    await state.broadcast({"action": "demo"})
    return "Initialisation du protocole de démonstration. Observez bien, Floriace."

@skill(
    "launch_app",
    risk="medium",
    help_text="Lance une application ou un logiciel sur l'ordinateur",
    describe=lambda d: f"Ouvrir l'application : {d.get('name')}"
)
async def launch_app(data: dict):
    from PHOEBUS.utils import launch_app as _launch
    name = data.get("name")
    if not name: return "Quelle application voulez-vous ouvrir ?"
    
    ok = _launch(name)
    if ok:
        return f"J'ai lancé {name}, Monsieur."
    return f"Je n'ai pas pu trouver l'application {name} sur ce système."

@skill(
    "mode_local",
    risk="low",
    help_text="Active ou désactive le mode IA locale (Ollama)",
    describe=lambda d: f"Passer en mode IA {'locale' if d.get('etat') == 'on' else 'hybride'}"
)
async def mode_local(data: dict):
    etat = data.get("etat", "on") == "on"
    if etat:
        os.environ["PHOEBUS_BRAIN_MODE"] = "privacy"
        return "Mode local activé. J'utilise désormais exclusivement Ollama."
    else:
        os.environ["PHOEBUS_BRAIN_MODE"] = "smart"
        return "Mode hybride réactivé. Je retrouve toute ma puissance cloud."
