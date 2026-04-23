# jarvis/automation.py
"""Moteur d'automatisation proactif et routines de fond de JARVIS."""
import time
import asyncio
import threading
from datetime import datetime

from jarvis.config import client
import jarvis.state as state
from jarvis.home import ha_get_etat, ha_lumiere, PIECES_LUMIERES
from jarvis.voice import parler
from jarvis.desktop import action_whatsapp_appel
from jarvis.config import pyautogui, IS_WINDOWS, client, Image, CHOSEN_MODEL, types
from jarvis.utils import open_uri
from jarvis.rag_memory import stocker_souvenir

# ── État des capteurs pour la détection de changements ──
DERNIERS_ETATS = {}
DERNIER_SCAN_VISION = 0

def envoyer_message_whatsapp(contact, message):
    """Envoie un message WhatsApp en arrière-plan."""
    if not pyautogui:
        print("[AUTOMATION] PyAutoGUI non dispo pour WhatsApp.")
        return False
    try:
        print(f"[AUTOMATION] Envoi WhatsApp à {contact}...")
        open_uri(f"whatsapp://send?text={message}")
        time.sleep(6) # Attente ouverture app
        
        # Chercher le contact
        pyautogui.hotkey('ctrl' if IS_WINDOWS else 'command', 'f')
        time.sleep(1)
        pyautogui.typewrite(contact)
        time.sleep(2)
        pyautogui.press('enter')
        time.sleep(2)
        
        # Taper et envoyer le message
        pyautogui.typewrite(message, interval=0.02)
        time.sleep(1)
        pyautogui.press('enter')
        time.sleep(1)
        
        # Fermer/Réduire la fenêtre (Optionnel, simuler Win+Down)
        if IS_WINDOWS:
            pyautogui.hotkey('win', 'down')
        return True
    except Exception as e:
        print(f"[AUTOMATION] Erreur WhatsApp message : {e}")
        return False


async def verifier_presence_floriace():
    """Détecte le retour à la maison via le capteur Home Assistant."""
    # Entités typiques pour la présence : 'person.floriace', 'device_tracker.sm_s921b'
    entites_presence = ["person.floriace", "device_tracker.sm_s921b"]
    
    for entite in entites_presence:
        etat_actuel = ha_get_etat(entite)
        
        if etat_actuel == "inconnu":
            continue
            
        etat_precedent = DERNIERS_ETATS.get(entite, etat_actuel)
        
        # Si Floriace passe de "not_home" (ou "away") à "home"
        if etat_precedent in ["not_home", "away"] and etat_actuel == "home":
            print("[AUTOMATION] Présence détectée : Floriace est rentré !")
            
            # 1. Allumer la lumière si c'est le soir (après 18h)
            heure = datetime.now().hour
            if heure >= 18 or heure < 7:
                ent_lumiere = PIECES_LUMIERES.get("salon", "light.salon")
                ha_lumiere(ent_lumiere, "on")
            
            # 2. Message d'accueil vocal
            moment = "Bonsoir" if heure >= 18 else "Bonjour"
            await parler(f"{moment} Floriace, bonne arrivée à la maison. L'environnement est configuré pour votre retour. Voulez-vous un résumé de votre journée ?")
            
        DERNIERS_ETATS[entite] = etat_actuel


async def verifier_rappels_proactifs():
    """Vérifie l'heure et envoie des rappels (ex: listes de courses si on part)."""
    # Exemple de logique : Si on est vendredi à 17h, envoyer un rappel de courses
    now = datetime.now()
    cle_rappel = f"courses_{now.strftime('%Y%m%d')}"
    
    if now.weekday() == 4 and now.hour == 17 and now.minute < 5: # Vendredi 17h00-17h05
        if not state.CLIENT_META.get(cle_rappel):
            state.CLIENT_META[cle_rappel] = True
            
            # Si Floriace est absent, envoyer par WhatsApp
            etat_presence = ha_get_etat("person.floriace")
            if etat_presence in ["not_home", "away"]:
                envoyer_message_whatsapp("Floriace", "Bonjour Monsieur. Pensez à faire les courses avant de rentrer ce soir. Bon retour.")
            else:
                await parler("Floriace, il est 17 heures. C'est le moment idéal pour penser aux courses du week-end.")


async def verifier_vision_passive():
    """Mode Garde : Capture l'écran silencieusement toutes les 5 minutes et l'analyse."""
    global DERNIER_SCAN_VISION
    now = time.time()
    
    # Toutes les 5 minutes (300 secondes)
    if now - DERNIER_SCAN_VISION > 300:
        DERNIER_SCAN_VISION = now
        etat_presence = ha_get_etat("person.floriace")
        
        # Inutile de scanner si Floriace n'est pas devant l'écran (absent ou écran en veille)
        # On va scanner quand même car on veut surveiller la machine.
        if not pyautogui or not Image or not client or not types:
            return
            
        try:
            import base64
            path_ss = "jarvis_passive_vision.png"
            screenshot = pyautogui.screenshot()
            screenshot.save(path_ss)
            img = Image.open(path_ss)
            
            prompt = (
                "Analyse silencieusement cet écran. Floriace est-il en train de travailler, "
                "de jouer, ou y a-t-il une anomalie grave visible (erreur code, écran bleu, piratage) ? "
                "Réponds avec UNE SEULE phrase descriptive. Commence par 'Anomalie:' s'il y a un vrai problème critique."
            )
            
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=CHOSEN_MODEL, 
                contents=[prompt, img]
            )
            
            texte = response.text.strip()
            # Stockage dans RAG pour la mémoire long terme
            stocker_souvenir(f"L'écran de Floriace montrait : {texte}", source="vision_passive")
            
            # Si anomalie, on prend la parole
            if texte.startswith("Anomalie:"):
                await parler(f"Pardonnez l'interruption Floriace. J'ai remarqué quelque chose sur votre écran : {texte.replace('Anomalie:', '')}")
                
            import os
            os.remove(path_ss)
        except Exception as e:
            print(f"[VISION PASSIVE] Erreur : {e}")

async def boucle_automatisation():
    """Boucle infinie exécutée en tâche de fond pour l'intelligence proactive."""
    print("[AUTOMATION] Moteur proactif démarré.")
    while True:
        try:
            # Ne pas interrompre si Jarvis parle ou écoute déjà
            if not state.is_speaking and not state.is_listening and not state.is_thinking:
                await verifier_presence_floriace()
                await verifier_rappels_proactifs()
                # await verifier_vision_passive()
                
            await asyncio.sleep(10) # Vérification toutes les 10 secondes
        except Exception as e:
            print(f"[AUTOMATION] Erreur boucle : {e}")
            await asyncio.sleep(30)


def demarrer_moteur_automatisation():
    """Démarre le moteur proactif dans un thread séparé avec sa propre boucle asyncio."""
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(boucle_automatisation())
        
    t = threading.Thread(target=run_loop, daemon=True, name="JarvisAutomation")
    t.start()
