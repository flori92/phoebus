from PHOEBUS.skills.registry import skill
from PHOEBUS import desktop as _desktop
import asyncio

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
    "system_control",
    risk="medium",
    help_text="Contrôle le matériel (verrouillage, mise en veille, volume)",
    describe=lambda d: f"Action système : {d.get('type')}"
)
async def system_control(data: dict):
    t = data.get("type")
    ok, msg = _desktop.system_control(t)
    return msg
