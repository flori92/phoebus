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
    "trier_complet",
    risk="medium",
    help_text="Organise et range automatiquement les fichiers du dossier actuel dans des sous-dossiers par type",
    describe=lambda _: "Organiser intelligemment vos fichiers par catégories"
)
async def trier_complet(data: dict):
    from PHOEBUS.desktop import lister_dossier
    import shutil
    
    EXTENSIONS_MAP = {
        "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
        "Videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm"],
        "Musique": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
        "Documents": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".csv"],
        "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
        "Code": [".py", ".js", ".html", ".css", ".java", ".cpp", ".c", ".json", ".sh", ".ts"]
    }
    
    current_dir = os.getcwd()
    fichiers = [f for f in os.listdir(current_dir) if os.path.isfile(os.path.join(current_dir, f))]
    
    compteurs = {}
    for f in fichiers:
        ext = os.path.splitext(f)[1].lower()
        found_cat = "Autres"
        for cat, list_ext in EXTENSIONS_MAP.items():
            if ext in list_ext:
                found_cat = cat
                break
        
        target_dir = os.path.join(current_dir, found_cat)
        os.makedirs(target_dir, exist_ok=True)
        shutil.move(os.path.join(current_dir, f), os.path.join(target_dir, f))
        compteurs[found_cat] = compteurs.get(found_cat, 0) + 1
        
    res = "Rangement terminé. " + ", ".join([f"{v} {k}" for k, v in compteurs.items()])
    return res

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
