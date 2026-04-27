from PHOEBUS.skills.registry import skill
from PHOEBUS.voice import parler
import asyncio

# Un exemple de mémoire simple pour les timers en cours
ACTIVE_TIMERS = {}

@skill(
    name="timer",
    risk="low",
    help_text="Lance un minuteur",
    describe=lambda d: f"Lancer un minuteur de {d.get('minutes', 0)} minutes et {d.get('secondes', 0)} secondes"
)
async def skill_timer(data: dict) -> str:
    m = int(data.get("minutes", 0))
    s = int(data.get("secondes", 0))
    label = data.get("label", "minuteur")
    
    total_seconds = m * 60 + s
    if total_seconds <= 0:
        return "La durée du minuteur est invalide."
        
    async def _run_timer(duration: int, name: str):
        await asyncio.sleep(duration)
        await parler(f"Floriace, le minuteur pour {name} est terminé !", keep_conversation=False)
        
    asyncio.create_task(_run_timer(total_seconds, label))
    return f"C'est noté. Minuteur pour {label} lancé pour {m} minutes et {s} secondes."
