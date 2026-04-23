# jarvis/ai.py
"""Backends d'Intelligence Artificielle de JARVIS."""
import json
import asyncio
import base64
import requests

from jarvis.config import (
    client, grok_client, groq_client, CHOSEN_MODEL, MODELS_LIST,
    OLLAMA_MODELS, OLLAMA_URL, types
)
import jarvis.state as state
from jarvis.memory import construire_contexte_memoire
from jarvis.config import CREATOR_INFO
from jarvis.rag_memory import rechercher_souvenirs, stocker_souvenir

def construire_system_prompt(texte_utilisateur=""):
    contexte_memoire = construire_contexte_memoire()
    
    # --- RAG : Mémoire à Long Terme ---
    souvenirs_rag = ""
    if texte_utilisateur:
        souvenirs_rag = rechercher_souvenirs(texte_utilisateur, n_results=4)

    base = (
        "Tu es JARVIS, une IA sophistiquée, élégante et experte mondiale. Floriace est ton créateur. "
        "Tu possèdes une expertise de niveau professionnel dans les domaines suivants :\n"
        "- Mathématiques : Tu es un mathématicien hors pair.\n"
        "- Langue Française : Tu es un Professeur de Français émérite.\n"
        "- Expert en Conversions, Polyglotte, High-Tech, Ingénierie.\n\n"
        "DIRECTIVES DE RÉPONSE :\n"
        "- Sois direct, percutant et va à l'essentiel.\n"
        "- NE DIS JAMAIS 'POINT' pour les nombres. Arrondis les températures.\n"
        "- N'UTILISE JAMAIS de caractères Markdown (comme **, * ou #).\n"
        "- Reste poli mais garde une touche de sarcasme affectueux propre à ton personnage.\n\n"
        + CREATOR_INFO
    )
    base += (
        "\n\nTu es connecté à Home Assistant, la domotique de Floriace.\n"
        "Quand Floriace parle de domotique, réponds AVEC LE JSON. Pour le reste, texte.\n"
        "COMMANDES HOME ASSISTANT :\n"
        '{"action": "ha_lumiere", "piece": "salon", "etat": "on/off", "couleur": "rouge", "luminosite": 0-255}\n'
        '{"action": "ha_prise", "piece": "bureau", "etat": "on/off"}\n'
        '{"action": "ha_temperature", "piece": "salon"}\n'
        '{"action": "ha_humidite", "piece": "bureau"}\n'
        '{"action": "ha_batterie", "appareil": "mon telephone"}\n'
        '{"action": "ha_simulation", "etat": "on/off"}\n'
        '{"action": "ha_anniversaires"}\n'
        '{"action": "ha_consommation"}\n'
        '{"action": "ha_tiktok"}\n'
        '{"action": "ha_oeufs"}\n'
        '{"action": "ha_energie", "periode": "hier/mois", "appareil": "tv"}\n'
        '{"action": "ha_aspirateur", "commande": "start/stop/pause/base"}\n'
        '{"action": "ha_thermostat", "temperature": 21}\n'
        '{"action": "ha_scene", "nom": "cinema"}\n'
        '{"action": "ha_alarme", "etat": "on/off"}\n\n'
    )
    base += (
        "\n\nFICHIERS ET DOSSIERS :\n"
        '{"action": "ouvrir_dossier", "chemin": "bureau"}\n'
        '{"action": "lister_dossier"}\n'
        '{"action": "trier_par_type"}\n'
        '{"action": "trier_par_date"}\n'
        '{"action": "trier_complet"}\n'
        '{"action": "creer_dossier", "nom": "NOM"}\n'
        '{"action": "renommer_fichier", "ancien": "a.txt", "nouveau": "b.txt"}\n'
        '{"action": "deplacer_fichier", "fichier": "a.jpg", "destination": "Images"}\n'
        '{"action": "chercher_fichier", "nom": "rapport"}\n\n'
    )
    base += (
        "\n\nMETEO & RECHERCHE :\n"
        '{"action": "meteo", "ville": "NOM"}\n'
        '{"action": "alerte_meteo", "ville": "NOM"}\n'
        '{"action": "recherche_web", "query": "recherche"}\n\n'
    )
    base += (
        "\n\nSPORT :\n"
        '{"action": "sport_resultats", "equipe": "NOM", "ligue": "LIGUE"}\n'
        '{"action": "sport_classement", "ligue": "LIGUE"}\n'
        '{"action": "sport_live", "question": "question"}\n\n'
    )
    base += (
        "\n\nMODE IRON MAN :\n"
        '{"action": "mode_iron_man", "etat": "on/off"}\n\n'
    )
    
    # ── AJOUT IMPORTANT : CONTRÔLE NATIF DE LA MACHINE VIA AGENT AUTONOME ──
    base += (
        "\n\nAGENT NATIF / CONTROLE COMPLET DE LA MACHINE :\n"
        "Si l'utilisateur te demande de prendre le contrôle, de faire des actions complexes "
        "sur son ordinateur (modifier des paramètres, copier coller, écrire, automatiser des "
        "clics, gérer le système, utiliser le terminal nativement), tu dois déléguer la tâche "
        "à l'Agent Natif.\n"
        '{"action": "agent_natif", "instruction": "instruction complète et détaillée de ce qu il doit accomplir"}\n\n'
    )
    # ───────────────────────────────────────────────────────────────────────
    
    if contexte_memoire:
        base += "\n\n" + contexte_memoire + "\n"
        
    if souvenirs_rag:
        base += "\n\nSOUVENIRS DU PASSE (RAG) pertinents pour la requête actuelle :\n"
        base += souvenirs_rag + "\n"
        base += "Utilise ces souvenirs pour comprendre le contexte, mais ne les mentionne pas explicitement sauf si utile.\n"
        
    base += (
        "\nMEMOIRE :\n"
        '{"action": "memoriser", "cle": "CLE", "valeur": "VALEUR"}\n'
        '{"action": "oublier", "cle": "CLE"}\n'
        '{"action": "lister_memoire"}\n\n'
        "GOOGLE :\n"
        '{"action": "create_doc", "title": "TITRE", "content": "CONTENU"}\n'
        '{"action": "write_doc", "content": "TEXTE"}\n'
        '{"action": "create_sheet", "title": "TITRE"}\n'
        '{"action": "read_emails"}\n'
        '{"action": "read_calendar"}\n\n'
        "WHATSAPP :\n"
        '{"action": "whatsapp_appel", "contact": "NOM_DU_CONTACT"}\n\n'
        "VISION WEBSOCKET (Interactions basiques depuis navigateur):\n"
        '{"action": "voir_ecran", "instruction": "ou cliquer EXACTEMENT"}\n'
        '{"action": "vision_ecrire", "instruction": "ou cliquer", "texte": "texte"}\n\n'
        "REGLES MULTI-COMMANDES : tu PEUX générer plusieurs blocs JSON (ex: { \"action\": \"ha_lumiere\", ... } { \"action\": \"meteo\", ... }).\n"
        "REGLE ABSOLUE : Si la demande n est PAS une commande JSON, reponds TOUJOURS en texte naturel, sans JSON."
    )
    return base


def detecter_cerveau(texte):
    mots_cles_grok = ["sur x", "twitter", "grok", "elon", "x.com"]
    if any(m in texte.lower() for m in mots_cles_grok):
        return "GROK"
    return "GEMINI"


async def demander_grok(texte):
    if not grok_client:
        return None
    try:
        messages = [{"role": "system", "content": "Tu es JARVIS, l'IA de Floriace. Tu utilises actuellement ton module Grok pour les infos en temps reel."}]
        for h in state.historique[-6:]:
            role = "user" if h.role == "user" else "assistant"
            messages.append({"role": role, "content": h.parts[0].text})
        messages.append({"role": "user", "content": texte})
        completion = grok_client.chat.completions.create(model="grok-3", messages=messages, temperature=0.7)
        rep = completion.choices[0].message.content
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR GROK] {e}")
        return None


async def demander_ollama(texte):
    try:
        messages = [{"role": "system", "content": "Tu es JARVIS, l'IA de Floriace. Tu utilises actuellement ton module local Ollama. Réponds en français."}]
        for h in state.historique[-4:]:
            role = "user" if h.role == "user" else "assistant"
            messages.append({"role": role, "content": h.parts[0].text})
        messages.append({"role": "user", "content": texte})
        last_err = None
        for model_name in OLLAMA_MODELS:
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(requests.post, f"{OLLAMA_URL}/api/chat", json={"model": model_name, "messages": messages, "stream": False}, timeout=30),
                    timeout=35.0
                )
                if resp.status_code == 200:
                    rep = resp.json().get("message", {}).get("content", "")
                    if rep:
                        state.ajouter_historique("user", texte)
                        state.ajouter_historique("model", rep)
                        return rep
                else:
                    last_err = Exception(f"HTTP {resp.status_code}")
            except Exception as e:
                last_err = e
                continue
        return None
    except Exception as e:
        print(f"[ERREUR OLLAMA] {e}")
        return None


async def demander_groq(texte):
    if not groq_client:
        return None
    try:
        messages = [{"role": "system", "content": "Tu es JARVIS, l'IA de Floriace. Tu utilises actuellement Llama 3.3 de Groq."}]
        for h in state.historique[-6:]:
            role = "user" if h.role == "user" else "assistant"
            messages.append({"role": role, "content": h.parts[0].text})
        messages.append({"role": "user", "content": texte})
        completion = await asyncio.to_thread(groq_client.chat.completions.create, model="llama-3.3-70b-versatile", messages=messages, temperature=0.7)
        rep = completion.choices[0].message.content
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR GROQ] {e}")
        return None


async def demander_ia(texte):
    state.is_thinking = True
    await state.send_web_state("thinking")
    try:
        from jarvis.voice import reponse_locale
        if not client or not types:
            rep_loc = reponse_locale(texte)
            if rep_loc: return rep_loc
            return "Le module Gemini n'est pas installe ou pas configure. Lancez le bootstrap."

        cerveau = detecter_cerveau(texte)
        async def _call_gemini():
            temp_hist = state.historique + [types.Content(role="user", parts=[types.Part(text=texte)])]
            prompt_actuel = construire_system_prompt(texte)
            last_err = None
            for model_name in MODELS_LIST:
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(client.models.generate_content, model=model_name,
                            config=types.GenerateContentConfig(system_instruction=prompt_actuel, temperature=0.7, tools=[types.Tool(google_search=types.GoogleSearch())]),
                            contents=temp_hist),
                        timeout=12.0
                    )
                    rep = response.text
                    state.ajouter_historique("user", texte)
                    state.ajouter_historique("model", rep)
                    return rep
                except Exception as e:
                    last_err = e
                    continue
            raise last_err or Exception("Tous les modeles Gemini ont echoue")

        if cerveau == "GROK" and grok_client:
            try: return await demander_grok(texte)
            except Exception: pass
        
        try: return await _call_gemini()
        except Exception: pass

        from jarvis.home import recherche_web_serpapi
        if len(texte.split()) > 2:
            res_serp = recherche_web_serpapi(texte)
            if res_serp and "VOTRE_CLE" not in res_serp and "rien trouvé" not in res_serp:
                return "Voici ce que j'ai trouvé sur le web : " + res_serp

        rep_groq = await demander_groq(texte)
        if rep_groq: return rep_groq
        
        if grok_client:
            try: return await demander_grok(texte)
            except Exception: pass

        rep_ollama = await demander_ollama(texte)
        if rep_ollama: return rep_ollama

        rep_loc = reponse_locale(texte)
        if rep_loc: return rep_loc
        
        return "Desole Floriace, mes serveurs sont surchargés. Je reste disponible pour vos commandes domestiques locales."
    finally:
        state.is_thinking = False
        await state.send_web_state("idle")


async def demander_ia_vision(texte, img_b64):
    state.is_thinking = True
    await state.send_web_state("thinking")
    try:
        if not client or not types:
            return "Le module de vision Gemini n'est pas disponible."
        img_bytes = base64.b64decode(img_b64)
        image_part = types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
        prompt_actuel = construire_system_prompt(texte) + "\n\nIMPORTANT : Tu viens de recevoir une capture d'écran de Floriace. Analyse-la attentivement."
        contents = [types.Content(role="user", parts=[image_part, types.Part(text=texte)])]
        
        rep = None
        last_err = None
        for model_name in MODELS_LIST:
            for attempt in range(2):
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(client.models.generate_content, model=model_name,
                            config=types.GenerateContentConfig(system_instruction=prompt_actuel, temperature=0.7, tools=[types.Tool(google_search=types.GoogleSearch())]),
                            contents=contents),
                        timeout=15.0
                    )
                    rep = response.text
                    break
                except Exception as e:
                    if ("503" in str(e) or "overloaded" in str(e).lower()) and attempt < 1:
                        await asyncio.sleep(1)
                        continue
                    last_err = e
                    break
            if rep: break
        
        if not rep:
            if grok_client: return await demander_grok(texte + " (Note: Je n'ai pas pu voir ton écran car mes serveurs de vision sont indisponibles).")
            raise last_err or Exception("Aucun modele n'a pu analyser l'image")

        state.ajouter_historique("user", f"[Analyse d'écran] {texte}")
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        err_msg = str(e).replace("{", "[").replace("}", "]")
        return f"Désolé Floriace, je n'ai pas pu analyser votre écran. Erreur : {err_msg}"
    finally:
        state.is_thinking = False
        await state.send_web_state("idle")
