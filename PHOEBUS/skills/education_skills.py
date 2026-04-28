import json
import os
from datetime import datetime
from pathlib import Path
from PHOEBUS.skills.registry import skill

# Chemin vers le fichier de données à la racine du projet
DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "etudiants_presence.json")

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"config": {"total_sessions": 0, "max_grade": 10, "last_session": "2026-04-28"}, "sessions": [], "students": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"config": {"total_sessions": 0, "max_grade": 10, "last_session": "2026-04-28"}, "sessions": [], "students": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def ajouter_etudiant(nom):
    data = load_data()
    if nom not in data["students"]:
        data["students"][nom] = {"presences": [], "excuses": [], "absences": []}
        save_data(data)
        return f"Étudiant {nom} ajouté."
    return "Déjà présent."

@skill(
    name="noter_etudiant",
    risk="low",
    help_text="Enregistre la présence ou l'absence d'un étudiant",
    describe=lambda d: f"Noter {d.get('nom')} comme {d.get('statut', 'présent')}"
)
async def skill_noter_etudiant(data: dict) -> str:
    nom = data.get("nom")
    statut = data.get("statut", "present")
    date = data.get("date")
    
    if not nom:
        return "Je n'ai pas le nom de l'étudiant."
        
    db = load_data()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    if date not in db["sessions"]:
        db["sessions"].append(date)
        db["config"]["total_sessions"] = len(db["sessions"])
    
    if nom not in db["students"]:
        db["students"][nom] = {"presences": [], "excuses": [], "absences": []}

    s = db["students"][nom]
    # Nettoyage des anciens statuts pour cette date
    for k in ["presences", "excuses", "absences"]:
        if date in s[k]: s[k].remove(date)
    
    # Ajout du nouveau statut
    if statut == "present": s["presences"].append(date)
    elif statut == "excuse": s["excuses"].append(date)
    else: s["absences"].append(date)
    
    save_data(db)
    return f"Fait. {nom} est marqué comme {statut} pour la séance du {date}."

@skill(
    name="calculer_notes_etudiants",
    risk="low",
    help_text="Génère le rapport final des notes de présence sur 10",
    describe=lambda _: "Calculer les notes finales de présence"
)
async def skill_calculer_notes(data: dict) -> str:
    db = load_data()
    total = db["config"]["total_sessions"]
    if total == 0: 
        return "Aucune séance n'a été enregistrée pour le moment."
    
    txt = "Voici le rapport des notes de présence sur 10 :\n\n"
    for nom, stats in db["students"].items():
        nb_valide = len(stats["presences"]) + len(stats["excuses"])
        note = round((nb_valide / total) * 10, 2)
        txt += f"- {nom} : {note}/10 ({len(stats['presences'])} présences, {len(stats['excuses'])} excuses).\n"
    
    return txt
