from PHOEBUS.skills.registry import skill
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from PHOEBUS.voice import parler
import datetime
import logging

# Désactiver les logs verbeux de apscheduler
logging.getLogger('apscheduler').setLevel(logging.WARNING)

scheduler = AsyncIOScheduler()
scheduler.start()

@skill(
    "schedule_task",
    risk="medium",
    help_text="Programme une tâche récurrente ou différée (ex: tous les matins à 8h)",
    describe=lambda d: f"Programmer l'action : {d.get('instruction')} ({d.get('recurrence')})"
)
async def schedule_task(data: dict):
    instruction = data.get("instruction")
    recurrence = data.get("recurrence") # 'daily', 'weekly', 'once'
    time_str = data.get("time") # 'HH:MM'
    
    if not instruction or not time_str:
        return "Données incomplètes pour la programmation."

    try:
        hour, minute = map(int, time_str.split(':'))
        
        async def _job():
            from PHOEBUS.router import route_request
            print(f"[SCHEDULER] Exécution de la tâche programmée : {instruction}")
            await route_request(instruction, source="scheduler")

        if recurrence == 'daily':
            scheduler.add_job(_job, 'cron', hour=hour, minute=minute)
            return f"C'est fait Floriace. J'exécuterai '{instruction}' tous les jours à {time_str}."
        
        elif recurrence == 'once':
            # Calcul du délai
            now = datetime.datetime.now()
            run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if run_time < now: run_time += datetime.timedelta(days=1)
            
            scheduler.add_job(_job, 'date', run_date=run_time)
            return f"Très bien. Je ferai cela une fois, à {time_str}."
            
        return f"Fréquence '{recurrence}' non supportée pour l'instant."
    except Exception as e:
        return f"Erreur lors de la programmation : {e}"

@skill(
    "list_scheduled_tasks",
    risk="low",
    help_text="Liste toutes les tâches automatiques programmées",
    describe=lambda _: "Lister les tâches programmées"
)
async def list_scheduled_tasks(data: dict):
    jobs = scheduler.get_jobs()
    if not jobs:
        return "Il n'y a aucune tâche programmée pour le moment."
    
    txt = "Voici vos tâches programmées :\n"
    for job in jobs:
        txt += f"- {job.next_run_time.strftime('%H:%M')} : {job.name}\n"
    return txt
