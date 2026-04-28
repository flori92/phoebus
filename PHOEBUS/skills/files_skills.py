from PHOEBUS.skills.registry import skill
from PHOEBUS import desktop as _desktop
import asyncio
import os

@skill(
    "ouvrir_dossier",
    risk="low",
    help_text="Ouvre un dossier sur votre Mac/PC",
    describe=lambda d: f"Ouvrir le dossier {d.get('chemin', 'bureau')}"
)
async def ouvrir_dossier(data: dict):
    path = data.get("chemin", "bureau")
    ok, msg = _desktop.ouvrir_dossier(path)
    return msg

@skill(
    "lister_dossier",
    risk="low",
    help_text="Affiche le contenu du dossier actuel",
    describe=lambda _: "Lister le contenu du dossier"
)
async def lister_dossier(data: dict):
    res, msg = _desktop.lister_dossier()
    return msg

@skill(
    "chercher_fichier",
    risk="low",
    help_text="Cherche un fichier sur votre ordinateur",
    describe=lambda d: f"Chercher le fichier nommé : {d.get('nom')}"
)
async def chercher_fichier(data: dict):
    nom = data.get("nom")
    return await asyncio.to_thread(_desktop.chercher_fichier, nom)

@skill(
    "creer_dossier",
    risk="low",
    help_text="Crée un nouveau dossier",
    describe=lambda d: f"Créer le dossier {d.get('nom')}"
)
async def skill_creer_dossier(data: dict):
    nom = data.get("nom")
    if not nom: return "Nom du dossier manquant."
    ok, msg = _desktop.creer_sous_dossier(nom)
    return msg

@skill(
    "renommer_fichier",
    risk="high",
    help_text="Renomme un fichier ou un dossier",
    describe=lambda d: f"Renommer {d.get('ancien')} en {d.get('nouveau')}"
)
async def skill_renommer_fichier(data: dict):
    ancien = data.get("ancien")
    nouveau = data.get("nouveau")
    if not ancien or not nouveau: return "Informations de renommage manquantes."
    ok, msg = _desktop.renommer_fichier(ancien, nouveau)
    return msg

@skill(
    "deplacer_fichier",
    risk="high",
    help_text="Déplace un fichier vers une destination",
    describe=lambda d: f"Déplacer {d.get('fichier')} vers {d.get('destination')}"
)
async def skill_deplacer_fichier(data: dict):
    fichier = data.get("fichier")
    dest = data.get("destination")
    if not fichier or not dest: return "Informations de déplacement manquantes."
    ok, msg = _desktop.deplacer_fichier(fichier, dest)
    return msg

@skill(
    "trier_par_type",
    risk="medium",
    help_text="Trie les fichiers par extension",
    describe=lambda _: "Trier les fichiers par type"
)
async def skill_trier_type(data: dict):
    ok, msg = _desktop.trier_par_type()
    return msg

@skill(
    "trier_par_date",
    risk="medium",
    help_text="Trie les fichiers par date de modification",
    describe=lambda _: "Trier les fichiers par date"
)
async def skill_trier_date(data: dict):
    ok, msg = _desktop.trier_par_date()
    return msg

@skill(
    "trier_complet",
    risk="medium",
    help_text="Organise et range automatiquement les fichiers du dossier actuel dans des sous-dossiers par type",
    describe=lambda _: "Organiser intelligemment vos fichiers par catégories"
)
async def trier_complet(data: dict):
    ok, msg = _desktop.trier_par_type_puis_date()
    return msg

@skill(
    "system_control",
    risk="medium",
    help_text="Contrôle le matériel (verrouillage, mise en veille, volume)",
    describe=lambda d: f"Action système : {d.get('type')}"
)
async def system_control(data: dict):
    t = data.get("type")
    ok, msg = _desktop.system_control(t)
    return msg
