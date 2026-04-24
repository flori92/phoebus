# jarvis/agent.py
"""Agent natif d'administration complète de la machine."""
import os
import time
import asyncio
import subprocess
import json
import base64
from pathlib import Path

from jarvis.config import (
    client, CHOSEN_MODEL, IS_WINDOWS, IS_MACOS, pyautogui, Image, types,
    groq_client, GROQ_MODEL, mistral_client, MISTRAL_MODEL
)
from jarvis.security import audit_log
from jarvis.utils import normalize_text
import jarvis.state as state


def executer_commande_shell(cmd: str) -> str:
    """Exécute une commande shell arbitraire et renvoie la sortie."""
    try:
        audit_log("shell_execution", command=cmd)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        output = result.stdout + result.stderr
        if not output:
            output = "Commande exécutée avec succès (sans sortie)."
        return output[:2000]  # On limite la taille pour ne pas exploser le contexte
    except subprocess.TimeoutExpired:
        return "La commande a expiré (timeout)."
    except Exception as e:
        return f"Erreur d'exécution: {e}"


def clavier_souris_action(action: str, params: dict) -> str:
    """Interface unifiée pour le contrôle natif du clavier et de la souris."""
    if not pyautogui:
        return "Contrôle clavier/souris indisponible (pyautogui manquant)."
    
    try:
        if action == "click":
            x, y = params.get("x"), params.get("y")
            button = params.get("button", "left")
            clicks = params.get("clicks", 1)
            if x is not None and y is not None:
                pyautogui.click(x=int(x), y=int(y), button=button, clicks=int(clicks))
            else:
                pyautogui.click(button=button, clicks=int(clicks))
            return "Clic effectué."
        
        elif action == "typewrite":
            text = params.get("text", "")
            interval = params.get("interval", 0.05)
            pyautogui.write(text, interval=float(interval))
            return f"Texte tapé: {text}"
            
        elif action == "press":
            key = params.get("key", "")
            if key:
                pyautogui.press(key)
                return f"Touche {key} pressée."
            return "Aucune touche spécifiée."
            
        elif action == "hotkey":
            keys = params.get("keys", [])
            if keys:
                pyautogui.hotkey(*keys)
                return f"Raccourci {keys} exécuté."
            return "Aucun raccourci spécifié."
            
        elif action == "scroll":
            clicks = params.get("amount", 0)
            pyautogui.scroll(int(clicks))
            return "Défilement effectué."
            
        elif action == "copy":
            pyautogui.hotkey('ctrl' if IS_WINDOWS else 'command', 'c')
            return "Copié."
            
        elif action == "paste":
            pyautogui.hotkey('ctrl' if IS_WINDOWS else 'command', 'v')
            return "Collé."
            
        elif action == "select_all":
            pyautogui.hotkey('ctrl' if IS_WINDOWS else 'command', 'a')
            return "Tout sélectionné."
            
    except Exception as e:
        return f"Erreur de contrôle matériel: {e}"
    
    return f"Action clavier/souris inconnue: {action}"


async def agent_vision_active() -> str:
    """Capture locale directe et transparente de l'écran pour analyse,
    sans passer par une demande d'autorisation via le navigateur (WebSocket).
    """
    if not client or not pyautogui or not Image:
        return "Erreur: Les modules de capture locale (pyautogui/Pillow) ou Gemini ne sont pas installés."
        
    try:
        # Capture directe silencieuse de l'écran hôte
        path_ss = "jarvis_agent_vision_temp.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(path_ss)
        
        # Encodage Base64
        with open(path_ss, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
        os.remove(path_ss)
        return encoded_string
    except Exception as e:
        print(f"[AGENT VISION] Erreur de capture locale directe: {e}")
        return None


async def orchestrer_agent_autonome(instruction: str) -> str:
    """Boucle principale de réflexion et d'action de l'agent natif.
    Il peut exécuter des commandes terminal, simuler le clavier/souris, 
    et 'voir' l'écran à volonté jusqu'à ce que la tâche soit finie.
    """
    print(f"\n[AGENT NATIF] Lancement de l'orchestration pour: '{instruction}'")
    
    # Prompt système surpuissant pour l'agent
    agent_prompt = """Tu es l'agent système natif de JARVIS. Tu possèdes un contrôle TOTAL sur la machine hôte.
Ton objectif est de satisfaire la demande de l'utilisateur de manière autonome.
Pour ce faire, tu peux générer l'UNE des commandes JSON suivantes à chaque itération.
Le système exécutera la commande et te renverra le résultat. Tu devras alors décider de la suite.

COMMANDES DISPONIBLES (réponds avec UN SEUL bloc JSON valide, rien d'autre):

1. Exécuter un script Python complet (ULTRA RAPIDE, pour automatiser des tâches complexes d'un coup):
{"action": "python_script", "code": "import os\\n..."}

2. Exécuter une ligne de commande (Terminal/Shell):
{"action": "shell", "cmd": "ta_commande_ici"}

3. Observer l'écran (capture locale directe et silencieuse):
{"action": "voir_ecran"}

4. Interagir avec la souris/clavier (clicks, frappe, raccourcis):
{"action": "clavier_souris", "type_action": "click|typewrite|press|hotkey", "params": {...}}

5. Déclarer la tâche terminée:
{"action": "terminer", "message": "Résumé"}

RÈGLES VITALES:
- Privilégie TOUJOURS `python_script` ou `shell` pour la rapidité (exécution < 1s).
- N'utilise la vision que si tu es bloqué sur une interface graphique pure.
"""
    
    historique_agent = [
        types.Content(role="user", parts=[types.Part(text=f"Tâche assignée: {instruction}")]),
    ]
    
    for etape in range(10):  # Limite de sécurité anti-boucle infinie
        try:
            print(f"[AGENT NATIF] Étape {etape+1}/10. L'agent réfléchit...")
            
            rep_text = ""
            # 1. Tentative Gemini (Recommandé pour Vision/Complexe)
            try:
                model_name = "gemini-2.0-flash" 
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=historique_agent,
                    config=types.GenerateContentConfig(
                        system_instruction=agent_prompt,
                        temperature=0.1,
                    ),
                )
                rep_text = response.text.strip()
            except Exception as e:
                print(f"[AGENT NATIF] Gemini indisponible ({str(e)[:50]}), repli...")
                # 2. Repli Groq (Llama 3.3) - Très efficace pour le JSON
                if groq_client:
                    try:
                        # Conversion historique pour OpenAI/Groq format
                        messages = [{"role": "system", "content": agent_prompt}]
                        for c in historique_agent:
                            role = "user" if c.role == "user" else "assistant"
                            messages.append({"role": role, "content": c.parts[0].text})
                        
                        comp = await asyncio.to_thread(
                            groq_client.chat.completions.create,
                            model=GROQ_MODEL,
                            messages=messages,
                            temperature=0.1
                        )
                        rep_text = comp.choices[0].message.content.strip()
                    except Exception as e2:
                        print(f"[AGENT NATIF] Groq indisponible, repli final...")
                        # 3. Repli final Mistral
                        if mistral_client:
                            messages = [{"role": "system", "content": agent_prompt}]
                            for c in historique_agent:
                                role = "user" if c.role == "user" else "assistant"
                                messages.append({"role": role, "content": c.parts[0].text})
                            comp = await asyncio.to_thread(
                                mistral_client.chat.completions.create,
                                model=MISTRAL_MODEL,
                                messages=messages,
                                temperature=0.1
                            )
                            rep_text = comp.choices[0].message.content.strip()
            
            if not rep_text:
                return "Aucun cerveau disponible pour l'agent natif."
            
            print(f"[AGENT NATIF] Pensée de l'agent: {rep_text[:100]}...")
            
            # Sauvegarder la pensée de l'agent
            historique_agent.append(types.Content(role="model", parts=[types.Part(text=rep_text)]))
            
            # Extraction du JSON
            start = rep_text.find('{')
            end = rep_text.rfind('}')
            if start == -1 or end == -1:
                # Si pas de JSON, on demande à l'agent d'être plus rigoureux au prochain tour
                historique_agent.append(types.Content(role="user", parts=[types.Part(text="ERREUR: Ta réponse ne contient pas de bloc JSON valide. Réponds UNIQUEMENT avec le JSON.")]))
                continue
                
            cmd_json = rep_text[start:end+1]
            try:
                # strict=False permet de gérer les sauts de ligne dans les chaînes de caractères
                data = json.loads(cmd_json, strict=False)
            except Exception as e:
                print(f"[AGENT NATIF] Erreur parsing JSON: {e}")
                historique_agent.append(types.Content(role="user", parts=[types.Part(text=f"ERREUR: JSON invalide ({e}). Vérifie ton formatage.")]))
                continue
            
            action = data.get("action")
            
            if action == "terminer":
                msg = data.get("message", "Tâche terminée.")
                print(f"[AGENT NATIF] Fin avec succès: {msg}")
                return msg
                
            elif action == "python_script":
                code = data.get("code", "")
                print(f"[AGENT NATIF] Exécute script Python...")
                # On écrit le code dans un fichier temporaire et on l'exécute
                with open("jarvis_tmp_script.py", "w") as f:
                    f.write(code)
                res = executer_commande_shell("python3 jarvis_tmp_script.py")
                os.remove("jarvis_tmp_script.py")
                historique_agent.append(types.Content(role="user", parts=[types.Part(text=f"Résultat script Python:\n{res}")]))

            elif action == "shell":
                cmd = data.get("cmd", "")
                print(f"[AGENT NATIF] Exécute: {cmd}")
                res = executer_commande_shell(cmd)
                historique_agent.append(types.Content(role="user", parts=[types.Part(text=f"Résultat shell:\n{res}")]))
                
            elif action == "clavier_souris":
                type_a = data.get("type_action")
                params = data.get("params", {})
                print(f"[AGENT NATIF] Interface humaine: {type_a} {params}")
                res = clavier_souris_action(type_a, params)
                historique_agent.append(types.Content(role="user", parts=[types.Part(text=f"Résultat clavier/souris:\n{res}")]))
                
            elif action == "voir_ecran":
                print(f"[AGENT NATIF] Capture d'écran locale en cours...")
                img_b64 = await agent_vision_active()
                if img_b64:
                    img_bytes = base64.b64decode(img_b64)
                    image_part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                    historique_agent.append(types.Content(role="user", parts=[
                        image_part, 
                        types.Part(text="Voici ce qui s'affiche actuellement sur l'écran hôte.")
                    ]))
                else:
                    historique_agent.append(types.Content(role="user", parts=[types.Part(text="Erreur: Impossible de capturer l'écran local.")]))
                    
            else:
                historique_agent.append(types.Content(role="user", parts=[types.Part(text="Action invalide reconnue. Choisis parmi: shell, voir_ecran, clavier_souris, terminer.")]))
                
        except Exception as e:
            print(f"[AGENT NATIF ERROR] {e}")
            return f"Le processus de l'agent a crashé: {e}"
            
    return "L'agent a atteint la limite de sécurité (10 étapes) sans avoir terminé."
