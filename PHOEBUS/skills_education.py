import json
import os
from datetime import datetime
from pathlib import Path

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "etudiants_presence.json")

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"config": {"total_sessions": 0, "max_grade": 10, "last_session": "2026-04-28"}, "sessions": [], "students": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

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

def noter_presence(nom, date=None, statut="present"):
    """statut: present, excuse, absent"""
    data = load_data()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    if date not in data["sessions"]:
        data["sessions"].append(date)
        data["config"]["total_sessions"] = len(data["sessions"])
    
    if nom not in data["students"]:
        ajouter_etudiant(nom)
        data = load_data()

    s = data["students"][nom]
    # Nettoyage des anciens statuts pour cette date
    for k in ["presences", "excuses", "absences"]:
        if date in s[k]: s[k].remove(date)
    
    # Ajout du nouveau statut
    if statut == "present": s["presences"].append(date)
    elif statut == "excuse": s["excuses"].append(date)
    else: s["absences"].append(date)
    
    save_data(data)
    return f"Note enregistrée pour {nom} ({statut}) le {date}."

def calculer_notes():
    data = load_data()
    total = data["config"]["total_sessions"]
    if total == 0: return "Aucune séance enregistrée."
    
    resultats = []
    for nom, stats in data["students"].items():
        nb_valide = len(stats["presences"]) + len(stats["excuses"])
        note = round((nb_valide / total) * 10, 2)
        resultats.append({
            "nom": nom,
            "note": note,
            "presences": len(stats["presences"]),
            "excuses": len(stats["excuses"]),
            "absences": len(stats["absences"])
        })
    
    return resultats
