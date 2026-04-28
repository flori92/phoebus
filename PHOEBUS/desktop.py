# PHOEBUS/desktop.py
"""Agent desktop PHOEBUS — gestion fichiers, apps, YouTube, WhatsApp, volume."""
import os
import time
import shutil
import webbrowser
from pathlib import Path
from datetime import datetime

from PHOEBUS.config import EXTENSIONS, pyautogui, IS_MACOS, IS_WINDOWS
from PHOEBUS.utils import special_folder, open_path, launch_app, desktop_file, open_uri
from PHOEBUS.security import audit_log
from PHOEBUS.home import chercher_youtube
import PHOEBUS.state as state


# ── Gestion fichiers ───────────────────────────────────────────────────────

def trouver_extension(ext):
    for categorie, extensions in EXTENSIONS.items():
        if ext.lower() in extensions:
            return categorie
    return "Autres"


def ouvrir_dossier(chemin):
    chemin = chemin.strip().strip('"').strip("'")
    chemin_resolu = special_folder(chemin)
    if not chemin_resolu.exists():
        return False, f"Dossier introuvable : {chemin_resolu}"
    state.dossier_courant = str(chemin_resolu)
    try:
        open_path(chemin_resolu)
    except Exception as e:
        return False, f"Dossier trouve mais impossible a ouvrir : {e}"
    return True, str(chemin_resolu)


def lister_dossier(chemin=None):
    cible = chemin or state.dossier_courant
    if not cible or not os.path.exists(cible):
        return None, "Aucun dossier ouvert ou chemin invalide."
    fichiers = []
    dossiers = []
    for item in os.scandir(cible):
        if item.is_file():
            fichiers.append(item.name)
        elif item.is_dir():
            dossiers.append(item.name)
    return {"chemin": cible, "fichiers": fichiers, "dossiers": dossiers}, None


def trier_par_type(chemin=None):
    cible = chemin or state.dossier_courant
    if not cible or not os.path.exists(cible):
        return False, "Aucun dossier ouvert."
    deplacements = 0
    erreurs      = 0
    categories   = {}
    for item in os.scandir(cible):
        if not item.is_file():
            continue
        ext       = Path(item.name).suffix
        categorie = trouver_extension(ext)
        dest_dir  = os.path.join(cible, categorie)
        try:
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, item.name)
            if os.path.exists(dest_path):
                base  = Path(item.name).stem
                ext2  = Path(item.name).suffix
                dest_path = os.path.join(dest_dir, f"{base}_{int(time.time())}{ext2}")
            shutil.move(item.path, dest_path)
            deplacements += 1
            categories[categorie] = categories.get(categorie, 0) + 1
        except Exception as e:
            print(f"[FICHIER] Erreur deplacement {item.name} : {e}")
            erreurs += 1
    resume = ", ".join([f"{v} {k}" for k, v in categories.items()])
    return True, f"{deplacements} fichiers tries : {resume}. {erreurs} erreurs."


def trier_par_date(chemin=None):
    cible = chemin or state.dossier_courant
    if not cible or not os.path.exists(cible):
        return False, "Aucun dossier ouvert."
    deplacements = 0
    erreurs      = 0
    for item in os.scandir(cible):
        if not item.is_file():
            continue
        try:
            mtime     = item.stat().st_mtime
            date      = datetime.fromtimestamp(mtime)
            annee     = str(date.year)
            mois      = date.strftime("%m - %B")
            dest_dir  = os.path.join(cible, annee, mois)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, item.name)
            if os.path.exists(dest_path):
                base      = Path(item.name).stem
                ext2      = Path(item.name).suffix
                dest_path = os.path.join(dest_dir, f"{base}_{int(time.time())}{ext2}")
            shutil.move(item.path, dest_path)
            deplacements += 1
        except Exception as e:
            print(f"[FICHIER] Erreur deplacement {item.name} : {e}")
            erreurs += 1
    return True, f"{deplacements} fichiers tries par date. {erreurs} erreurs."


def trier_par_type_puis_date(chemin=None):
    cible = chemin or state.dossier_courant
    if not cible or not os.path.exists(cible):
        return False, "Aucun dossier ouvert."
    ok1, msg1 = trier_par_type(cible)
    if not ok1:
        return False, msg1
    for item in os.scandir(cible):
        if item.is_dir() and item.name in EXTENSIONS.keys():
            trier_par_date(item.path)
    return True, "Dossier trie par type puis par date dans chaque categorie."


def creer_sous_dossier(nom, chemin=None):
    cible = chemin or state.dossier_courant
    if not cible:
        return False, "Aucun dossier ouvert."
    nouveau = os.path.join(cible, nom)
    try:
        os.makedirs(nouveau, exist_ok=True)
        return True, f"Dossier {nom} cree."
    except Exception as e:
        return False, f"Erreur creation dossier : {e}"


def renommer_fichier(ancien_nom, nouveau_nom, chemin=None):
    cible = chemin or state.dossier_courant
    if not cible:
        return False, "Aucun dossier ouvert."
    ancien  = os.path.join(cible, ancien_nom)
    nouveau = os.path.join(cible, nouveau_nom)
    try:
        os.rename(ancien, nouveau)
        return True, f"Fichier renomme en {nouveau_nom}."
    except Exception as e:
        return False, f"Erreur renommage : {e}"


def deplacer_fichier(nom_fichier, dossier_dest, chemin=None):
    cible = chemin or state.dossier_courant
    if not cible:
        return False, "Aucun dossier ouvert."
    source = os.path.join(cible, nom_fichier)
    dest   = os.path.join(cible, dossier_dest, nom_fichier)
    try:
        os.makedirs(os.path.join(cible, dossier_dest), exist_ok=True)
        shutil.move(source, dest)
        return True, f"{nom_fichier} deplace dans {dossier_dest}."
    except Exception as e:
        return False, f"Erreur deplacement : {e}"


def chercher_fichier(nom, chemin=None):
    cible = chemin or state.dossier_courant
    if not cible:
        return [], "Aucun dossier ouvert."
    resultats = []
    for root, dirs, files in os.walk(cible):
        for f in files:
            if nom.lower() in f.lower():
                resultats.append(os.path.join(root, f))
    return resultats, None


# ── Actions PC directes ────────────────────────────────────────────────────

def system_control(action_type):
    """Contrôle matériel du système (optimisé pour macOS)."""
    try:
        if IS_MACOS:
            if action_type == "lock":
                os.system('open -a ScreenSaverEngine')
            elif action_type == "sleep":
                os.system('osascript -e "tell application \\"System Events\\" to sleep"')
            elif action_type == "empty_trash":
                os.system('osascript -e "tell application \\"Finder\\" to empty trash"')
            elif action_type == "screensaver":
                os.system('open -a ScreenSaverEngine')
            return True, f"Action système {action_type} exécutée sur Mac."
        elif IS_WINDOWS:
            if action_type == "lock":
                os.system('rundll32.exe user32.dll,LockWorkStation')
            elif action_type == "sleep":
                os.system('rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
            return True, f"Action système {action_type} exécutée sur Windows."
        return False, "OS non supporté pour cette action."
    except Exception as e:
        return False, str(e)


def executer_action_pc(commande):
    cmd = commande.lower()

    if "met de la musique" in cmd or "mets de la musique" in cmd:
        url = "https://www.youtube.com/watch?v=7CGKeID7nRc&list=PL4fGSI1pDJn50iCQRUVmgUjOrCggCQ9nR"
        webbrowser.open(url, new=2)
        time.sleep(6)
        if pyautogui:
            pyautogui.press('f')
        return "C'est parti Floriace, je mets votre playlist en plein écran."

    if "youtube" in cmd:
        recherche = cmd
        for mot in ["mets", "joue", "lance", "la video", "sur youtube", "youtube", "PHOEBUS"]:
            recherche = recherche.replace(mot, "")
        recherche = recherche.strip()
        if recherche:
            url = chercher_youtube(recherche)
            if url:
                webbrowser.open(url, new=2)
                time.sleep(5)
                if pyautogui:
                    pyautogui.press('f')
                return f"Je lance {recherche} sur YouTube."
        return "Video introuvable."

    if "ouvre" in cmd or "lance" in cmd:
        if "chrome" in cmd:
            return "Chrome ouvert." if launch_app("chrome") else "Je n'ai pas trouve Chrome sur cet environnement."
        if "notepad" in cmd or "bloc-notes" in cmd:
            return "Bloc-notes ouvert." if launch_app("notepad") else "Je n'ai pas trouve d'editeur texte compatible."
        if "explorateur" in cmd:
            return "Explorateur ouvert." if launch_app("explorer") else "Je n'ai pas trouve de gestionnaire de fichiers compatible."

    if "volume" in cmd:
        if not pyautogui:
            return "Controle du volume indisponible sur cet environnement."
        if "monte" in cmd or "augmente" in cmd:
            for _ in range(5):
                pyautogui.press('volumeup')
            return "Volume augmente."
        if "baisse" in cmd:
            for _ in range(5):
                pyautogui.press('volumedown')
            return "Volume baisse."
        if "coupe" in cmd:
            pyautogui.press('volumemute')
            return "Son coupe."

    if "screenshot" in cmd or "capture" in cmd:
        if not pyautogui:
            return "Capture d'ecran indisponible sur cet environnement."
        path = desktop_file("screenshot.png")
        pyautogui.screenshot(str(path))
        return f"Screenshot sauvegarde dans {path}."

    if "eteins" in cmd or "shutdown" in cmd:
        if "confirme" not in cmd and "confirm" not in cmd:
            return "Commande sensible. Dites 'PHOEBUS confirme extinction' pour eteindre cette machine."
        from PHOEBUS.utils import shutdown_system
        shutdown_system(5)
        audit_log("pc_shutdown_requested", source="voice_command")
        return "Extinction dans 5 secondes."

    return None


# ── WhatsApp ───────────────────────────────────────────────────────────────

async def action_whatsapp_appel(contact, parler_fn):
    """Lance un appel WhatsApp. parler_fn est passé pour éviter l'import circulaire."""
    if not pyautogui:
        await parler_fn("Controle souris clavier indisponible, je ne peux pas piloter WhatsApp sur cet environnement.")
        return False
    try:
        await parler_fn(f"J'appelle {contact} sur WhatsApp, Floriace.")
        open_uri("whatsapp://")
        time.sleep(6)
        pyautogui.hotkey('ctrl' if IS_WINDOWS else 'command', 'f')
        time.sleep(1)
        pyautogui.typewrite(contact)
        time.sleep(2)
        pyautogui.press('enter')
        time.sleep(3)
        print(f"[WHATSAPP] Envoi du raccourci d'appel (Ctrl+Shift+C)...")
        pyautogui.hotkey('ctrl' if IS_WINDOWS else 'command', 'shift', 'c')
        time.sleep(2)
        print(f"[WHATSAPP] Verification par vision au cas ou...")
        from PHOEBUS.vision import PHOEBUS_vision_cliquer
        await PHOEBUS_vision_cliquer("clique sur le bouton 'Appel vocal' ou l icone de telephone qui vient de s afficher en haut a droite")
        return True
    except Exception as e:
        print(f"[WHATSAPP ERROR] {e}")
        await parler_fn(f"Desole Floriace, je n'ai pas pu lancer l'appel WhatsApp. {e}")
        return False
