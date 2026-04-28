from PHOEBUS.skills.registry import skill
from PHOEBUS.voice import parler
from PHOEBUS import timers as _timers
import asyncio
import time

@skill(
    name="timer",
    risk="low",
    help_text="Lance un minuteur ou un rappel",
    describe=lambda d: f"Lancer un {d.get('kind', 'minuteur')} de {d.get('minutes', 0)} min {d.get('secondes', 0)} s"
)
async def skill_timer(data: dict) -> str:
    m = int(data.get("minutes", 0))
    s = int(data.get("secondes", 0))
    label = data.get("label", "").strip()
    kind = data.get("kind", "timer")
    
    total_seconds = m * 60 + s
    if total_seconds <= 0:
        return "Durée invalide, Monsieur."
        
    _timers.set_timer(total_seconds, label, kind=kind)
    fmt = _timers.format_duration(total_seconds)
    
    if kind == "rappel":
        return f"C'est noté. Rappel programmé dans {fmt}" + (f" : {label}." if label else ".")
    return f"Très bien. Minuteur lancé sur {fmt}" + (f" pour {label}." if label else ".")

@skill(
    name="timer_list",
    risk="low",
    help_text="Affiche la liste des minuteurs et rappels en cours",
    describe=lambda _: "Lister les minuteurs actifs"
)
async def skill_timer_list(data: dict) -> str:
    items = _timers.list_timers()
    if not items:
        return "Aucun minuteur ni rappel n'est actif pour le moment."
        
    lignes = []
    for it in items[:6]:
        remaining = max(0, it.get("due_ts", 0) - time.time())
        fmt = _timers.format_duration(remaining)
        label = it.get("label") or ""
        k = it.get("kind", "timer")
        prefix = "rappel" if k == "rappel" else "minuteur"
        lignes.append(f"un {prefix} dans {fmt}" + (f" : {label}" if label else ""))
        
    return "Il vous reste : " + ", et ".join(lignes) + "."

@skill(
    name="timer_cancel",
    risk="low",
    help_text="Annule un minuteur ou un rappel via son ID",
    describe=lambda d: f"Annuler le minuteur {d.get('id')}"
)
async def skill_timer_cancel(data: dict) -> str:
    tid = data.get("id")
    if tid and _timers.cancel_timer(int(tid)):
        return "C'est fait, j'ai annulé ce minuteur."
    return "Je n'ai pas trouvé de minuteur correspondant à cette demande."
