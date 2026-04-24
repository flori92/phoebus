# PHOEBUS/vision.py
"""Vision PHOEBUS — capture d'écran, analyse IA, clic/saisie automatiques."""
import os
import json
import time
import uuid
import asyncio

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
        return f"C'est fait Floriace. J'ai saisi '{texte_a_taper}' dans {instruction}."
    except Exception as e:
        print(f"[VISION ERROR] {e}")
        return "J'ai eu un petit souci technique pour taper le texte, Floriace."
