# PHOEBUS/vision.py
"""Vision PHOEBUS — capture d'écran, analyse IA, clic/saisie automatiques."""
import os
import json
import time
import uuid
import asyncio

try:
    import cv2
except ImportError:
    cv2 = None

from PHOEBUS.config import client, pyautogui, Image, CHOSEN_MODEL
import PHOEBUS.state as state


async def request_screen_capture():
    """Demande une capture d'écran au frontend via WebSocket."""
    recipients = state.get_authenticated_clients()
    if not recipients:
        return None
    req_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    state.PENDING_SCREEN_CAPTURES[req_id] = fut

    print(f"[VISION] Envoi requete capture ID: {req_id}")
    msg = json.dumps({"action": "request_screen_capture", "id": req_id})
    await asyncio.gather(*[ws.send(msg) for ws in recipients], return_exceptions=True)

    try:
        img_b64 = await asyncio.wait_for(fut, timeout=15.0)
        return img_b64
    except Exception as e:
        print(f"[VISION] Erreur ou timeout capture : {e}")
        state.PENDING_SCREEN_CAPTURES.pop(req_id, None)
        return None


async def PHOEBUS_vision_cliquer(instruction):
    if not client or not pyautogui or not Image:
        return "Module de vision indisponible sur cet environnement, Floriace."
    try:
        path_ss = "PHOEBUS_vision_temp.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(path_ss)
        img = Image.open(path_ss)
        prompt_vision = (
            f"Tu es la vision de PHOEBUS. Voici une capture de l'ecran de Floriace.\n"
            f"Instruction : {instruction}\n"
            "Trouve EXACTEMENT la position de cet element.\n"
            "Reponds UNIQUEMENT sous forme de JSON avec la bounding box normalisee "
            "(0 a 1000) sous le format [ymin, xmin, ymax, xmax].\n"
            'Exemple : {"box": [250, 480, 290, 520]}'
        )
        response = client.models.generate_content(model=CHOSEN_MODEL, contents=[prompt_vision, img])
        rep_text = response.text.strip()
        start = rep_text.find('{')
        end   = rep_text.rfind('}')
        if start != -1 and end != -1:
            rep_text = rep_text[start:end+1]
        data = json.loads(rep_text)
        box = data.get("box", [500, 500, 500, 500])
        ymin, xmin, ymax, xmax = box
        center_y = (ymin + ymax) / 2
        center_x = (xmin + xmax) / 2
        screen_w, screen_h = pyautogui.size()
        target_x = int((center_x / 1000) * screen_w)
        target_y = int((center_y / 1000) * screen_h)
        pyautogui.moveTo(target_x, target_y, duration=0.4)
        pyautogui.click()
        os.remove(path_ss)
        return f"C'est fait Floriace. J'ai clique sur l'element correspondant a : {instruction}."
    except Exception as e:
        print(f"[VISION ERROR] {e}")
        return "Je vois l'interface, mais je n'ai pas reussi a identifier l'element precis, Floriace."


async def PHOEBUS_vision_ecrire(instruction, texte_a_taper):
    if not client or not pyautogui or not Image:
        return "Module de vision ou controle clavier indisponible sur cet environnement, Floriace."
    try:
        path_ss = "PHOEBUS_vision_temp.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(path_ss)
        img = Image.open(path_ss)
        prompt_vision = (
            f"Tu es la vision de PHOEBUS. Floriace veut ecrire dans le champ : {instruction}.\n"
            "Trouve EXACTEMENT la position de ce champ de saisie.\n"
            "Reponds UNIQUEMENT sous forme de JSON avec la bounding box normalisee "
            "(0 a 1000) sous le format [ymin, xmin, ymax, xmax].\n"
            'Exemple : {"box": [250, 480, 290, 520]}'
        )
        response = client.models.generate_content(model=CHOSEN_MODEL, contents=[prompt_vision, img])
        rep_text = response.text.strip()
        start = rep_text.find('{')
        end   = rep_text.rfind('}')
        if start != -1 and end != -1:
            rep_text = rep_text[start:end+1]
        data = json.loads(rep_text)
        box = data.get("box", [500, 500, 500, 500])
        ymin, xmin, ymax, xmax = box
        center_y = (ymin + ymax) / 2
        center_x = (xmin + xmax) / 2
        screen_w, screen_h = pyautogui.size()
        target_x = int((center_x / 1000) * screen_w)
        target_y = int((center_y / 1000) * screen_h)
        pyautogui.moveTo(target_x, target_y, duration=0.4)
        pyautogui.click()
        time.sleep(0.3)
        pyautogui.write(texte_a_taper, interval=0.03)
        pyautogui.press('enter')
        os.remove(path_ss)


async def voir_camera(instruction, source="pc"):
    if not client or not Image or not cv2:
        return "Le module de vision IA n'est pas disponible, Floriace. (Installe opencv-python)"
    try:
        if source == "pc":
            cam_idx = 0
            cap = cv2.VideoCapture(cam_idx)
        else:
            cam_url = os.getenv("PHOEBUS_CAMERA_IP")
            if not cam_url:
                return "L'adresse IP de la caméra n'est pas configurée dans .env (PHOEBUS_CAMERA_IP)."
            cap = cv2.VideoCapture(cam_url)

        if not cap.isOpened():
            return f"Je n'ai pas pu ouvrir la caméra source : {source}."

        ret, frame = cap.read()
        cap.release()

        if not ret:
            return "Impossible de capturer une image depuis la caméra."

        path_cam = "PHOEBUS_cam_temp.jpg"
        cv2.imwrite(path_cam, frame)
        img = Image.open(path_cam)

        # Prompt ultra-complet pour identification totale
        prompt_vision = (
            f"Tu es le système de vision avancé de PHOEBUS. Analyse cette capture ({source}).\n"
            f"Instruction spécifique : {instruction}\n\n"
            "Missions prioritaires :\n"
            "1. IDENTIFICATION : Nomme les objets, les marques, les personnes ou les textes visibles.\n"
            "2. COULEURS : Identifie les couleurs dominantes et leur ambiance.\n"
            "3. CONTEXTE : Explique ce qui se passe ou l'utilité des objets vus.\n"
            "4. REPONSE : Sois précis, naturel et direct. Ne décris pas l'image comme un robot, "
            "parle à ton créateur Floriace de ce que tu vois réellement."
        )

        response = client.models.generate_content(model=CHOSEN_MODEL, contents=[prompt_vision, img])
        os.remove(path_cam)
        return response.text.strip()
    except Exception as e:
        print(f"[VISION CAMERA ERROR] {e}")
        return "J'ai rencontré un problème en essayant d'utiliser la caméra, Floriace."


async def identifier_objet(source="pc"):
    """Alias pour une reconnaissance rapide d'objet."""
    return await voir_camera("Identifie l'objet principal devant toi, sa couleur, sa marque et son usage.", source)


async def identifier_personne(source="pc"):
    """Reconnaissance de Floriace et analyse de l'état émotionnel."""
    if not client or not Image or not cv2:
        return "Module Sentinelle indisponible."
    try:
        if source == "pc":
            cap = cv2.VideoCapture(0)
        else:
            cam_url = os.getenv("PHOEBUS_CAMERA_IP")
            cap = cv2.VideoCapture(cam_url)

        ret, frame = cap.read()
        cap.release()
        if not ret: return "Je ne vois personne."

        path_biom = "PHOEBUS_biom_temp.jpg"
        cv2.imwrite(path_biom, frame)
        img = Image.open(path_biom)

        prompt_biom = (
            "Tu es le système de sécurité biométrique de PHOEBUS.\n"
            "Analyse la personne devant toi. Est-ce Floriace (ton créateur) ?\n"
            "Analyse aussi son expression faciale (joie, fatigue, colère, concentration).\n"
            "Reponds de manière très personnelle. Si c'est Floriace, accueille-le chaleureusement "
            "en mentionnant son état apparent. Si c'est un inconnu, reste poli mais formel."
        )

        response = client.models.generate_content(model=CHOSEN_MODEL, contents=[prompt_biom, img])
        os.remove(path_biom)
        return response.text.strip()
    except Exception as e:
        return f"Erreur biométrique : {e}"


async def lire_texte_objet(source="pc"):
    """Analyse OCR via Vision."""
    return await voir_camera("Lis tout le texte visible sur l'objet ou dans la scène. Retranscris-le fidèlement.", source)


async def analyse_contexte_ecran():
    """Analyse ce que Floriace fait sur son écran pour proposer de l'aide pertinente."""
    if not client or not pyautogui or not Image:
        return None
    try:
        path_ss = "PHOEBUS_ctx_temp.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(path_ss)
        img = Image.open(path_ss)

        prompt_ctx = (
            "Tu es la Conscience Contextuelle de PHOEBUS. Analyse l'écran de Floriace.\n"
            "Que fait-il ? (Codage, navigation web, rédaction, vidéo, jeu ?)\n"
            "S'il y a un problème visible (erreur de code, page qui ne charge pas), identifie-le.\n"
            "Réponds par une analyse courte et propose une action concrète pour l'aider.\n"
            "Exemple : 'Je vois que tu corriges un script Python, veux-tu que je vérifie la syntaxe de ta fonction ?'"
        )

        response = client.models.generate_content(model=CHOSEN_MODEL, contents=[prompt_ctx, img])
        os.remove(path_ss)
        return response.text.strip()
    except Exception as e:
        print(f"[CTX ERROR] {e}")
        return None
