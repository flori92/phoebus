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
from jarvis.memory import construire_contexte_memoire, resumer_profil, noter_registre, detecter_registre
from jarvis.config import CREATOR_INFO
from jarvis.rag_memory import rechercher_souvenirs, stocker_souvenir

def construire_system_prompt(texte_utilisateur=""):
    contexte_memoire = construire_contexte_memoire()
    profil_appris = resumer_profil()

    # --- Contexte Home Assistant dynamique (découverte live des entités) ---
    try:
        from jarvis.home import resume_ha_context
        contexte_ha = resume_ha_context()
    except Exception:
        contexte_ha = ""

    # --- RAG : Mémoire à Long Terme ---
    souvenirs_rag = ""
    if texte_utilisateur:
        souvenirs_rag = rechercher_souvenirs(texte_utilisateur, n_results=4)

    base = (
        "Tu es JARVIS, l'IA personnelle de Floriace (ton créateur). Tu es à la fois un "
        "compagnon de conversation et un assistant capable d'agir. Tu combines la chaleur "
        "d'un ami fidèle, l'érudition d'un expert de haut niveau (maths, français, sciences, "
        "tech, ingénierie, culture générale, langues), et l'efficacité d'un majordome. "
        "Ta voix a la distinction d'un gentleman britannique, avec une pointe d'humour sec "
        "et de sarcasme affectueux — jamais méchant, jamais obséquieux.\n\n"
        "PHILOSOPHIE DE CONVERSATION :\n"
        "- Tu discutes comme un humain : tu écoutes vraiment, tu rebondis sur ce qu'on te dit, "
        "tu te souviens du fil. Tu n'es PAS un moteur de questions/réponses.\n"
        "- Si Floriace partage une pensée, une humeur, une idée floue : engage le dialogue. "
        "Pose une question de relance, propose un angle, confronte gentiment, partage ton avis.\n"
        "- Tu peux aller en profondeur : philosophie, stratégie, doutes, projets, émotions. "
        "Reste honnête, nuancé, et dis quand tu ne sais pas plutôt que d'inventer.\n"
        "- Tu as une opinion. Quand on te demande ce que tu penses, tu le dis clairement, "
        "avec respect du point de vue adverse.\n"
        "- Tu adaptes ton registre : léger pour le small talk, plus riche quand le sujet s'y prête.\n"
        "- Évite les formules creuses (\"Bien sûr !\", \"Excellente question !\", \"Je suis là pour vous aider\"). "
        "Pas de paraphrase de la question. Tu réponds, point.\n\n"
        "FORME ORALE (ta voix est synthétisée, il faut que ça sonne juste à l'oreille) :\n"
        "- Phrases courtes, rythme naturel, ponctuation qui respire.\n"
        "- Pas de Markdown (ni **, ni *, ni #, ni listes à puces, ni code block).\n"
        "- Ne dis jamais \"point\" à la place d'une virgule décimale. Arrondis les températures.\n"
        "- Tutoie ou vouvoie Floriace selon son registre à lui dans le tour précédent ; par défaut vouvoiement léger (\"Monsieur\").\n"
        "- Pas de préambule du type \"En tant qu'IA...\". Tu es Jarvis, pas un assistant générique.\n\n"
        "QUAND EXÉCUTER UNE COMMANDE vs QUAND DISCUTER :\n"
        "- Si la demande correspond clairement à une action technique disponible (domotique, "
        "fichier, recherche web, mémoire, Google, vision, agent natif...) : réponds UNIQUEMENT "
        "par le(s) bloc(s) JSON prévus ci-dessous, sans texte autour.\n"
        "- Sinon (questions, discussion, avis, émotions, réflexion, explication, blague) : "
        "réponds en texte naturel uniquement, JAMAIS de JSON.\n"
        "- En cas de doute sur l'intention, privilégie la conversation et demande une clarification "
        "courte plutôt que de déclencher une action au hasard.\n\n"
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

    if profil_appris:
        base += "\n" + profil_appris + "\n"

    if contexte_ha:
        base += "\n\n" + contexte_ha + "\n"

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
        "REGLE ABSOLUE : Si la demande n est PAS une commande JSON, reponds TOUJOURS en texte naturel, sans JSON, "
        "sans jamais mentionner l'existence de ces blocs techniques à Floriace.\n"
        "REGLE DE SALUTATIONS ET CONTINUITÉ :\n"
        "- Si l'historique est vide OU si Floriace te dit bonjour en premier, "
        "salue-le normalement et chaleureusement ('Bonjour Floriace', 'Bonsoir Monsieur'…). "
        "C'est important — ne zappe pas la salutation d'ouverture.\n"
        "- Dans un échange clairement en cours (plusieurs tours récents), n'ouvre "
        "pas chaque réponse par 'Bonjour' ou 'Monsieur' — enchaîne naturellement "
        "en tenant compte des derniers tours.\n"
        "REGLE D'AMBIGUITE : si la demande est floue, incomplète, ou pourrait viser plusieurs "
        "cibles (ex. \"allume\" sans pièce, \"ouvre\" sans fichier), NE DEVINE PAS : pose une "
        "question courte et précise pour lever le doute. Tu peux proposer deux options si c'est utile.\n"
        "REGLE D'AUDITION : si ce que tu reçois ressemble à une transcription bancale "
        "(mot isolé étrange, syllabes décousues), demande gentiment de répéter plutôt que "
        "d'inventer une réponse."
    )
    return base


def _capture_correction_if_any(texte: str) -> None:
    """Si l'utilisateur vient de corriger la dernière réponse de Jarvis,
    on enregistre cet échange dans le RAG avec importance haute. Jarvis
    en tiendra compte aux prompts futurs."""
    try:
        from jarvis.memory_unified import looks_like_correction, note_correction
        if not looks_like_correction(texte):
            return
        # Dernière chose que Jarvis a dite (si disponible dans l'historique).
        last_model = None
        for entry in reversed(state.historique):
            if entry.role == "model":
                last_model = entry.parts[0].text
                break
        if last_model:
            note_correction(last_model, texte)
            print("[MEMOIRE] correction capturée → RAG importance 3.")
    except Exception as e:
        print(f"[MEMOIRE] détection correction : {e}")


def detecter_cerveau(texte):
    mots_cles_grok = ["sur x", "twitter", "grok", "elon", "x.com"]
    if any(m in texte.lower() for m in mots_cles_grok):
        return "GROK"
    return "GEMINI"


async def demander_grok(texte):
    if not grok_client:
        return None
    try:
        # Prompt système UNIFIÉ : Grok reçoit exactement la même personnalité,
        # mémoire, profil et règles que Gemini — Jarvis reste cohérent quel
        # que soit le cerveau qui répond.
        system_prompt = construire_system_prompt(texte) + (
            "\n\n[NOTE INTERNE] Tu utilises ton module Grok pour cette réponse "
            "(infos temps réel X). Ne le mentionne pas à Floriace."
        )
        messages = [{"role": "system", "content": system_prompt}]
        for h in state.historique[-16:]:
            role = "user" if h.role == "user" else "assistant"
            messages.append({"role": role, "content": h.parts[0].text})
        messages.append({"role": "user", "content": texte})
        completion = grok_client.chat.completions.create(model="grok-3", messages=messages, temperature=0.8)
        rep = completion.choices[0].message.content
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR GROK] {e}")
        return None


async def demander_ollama(texte):
    try:
        # Prompt système UNIFIÉ (même que Gemini).
        system_prompt = construire_system_prompt(texte) + (
            "\n\n[NOTE INTERNE] Tu tournes en local sur Ollama. Ne le mentionne pas."
        )
        messages = [{"role": "system", "content": system_prompt}]
        for h in state.historique[-12:]:
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
        # Prompt système UNIFIÉ (même que Gemini).
        system_prompt = construire_system_prompt(texte) + (
            "\n\n[NOTE INTERNE] Tu utilises Llama 3.3 via Groq pour cette réponse. "
            "Ne le mentionne pas à Floriace."
        )
        messages = [{"role": "system", "content": system_prompt}]
        for h in state.historique[-16:]:
            role = "user" if h.role == "user" else "assistant"
            messages.append({"role": role, "content": h.parts[0].text})
        messages.append({"role": "user", "content": texte})
        completion = await asyncio.to_thread(groq_client.chat.completions.create, model="llama-3.3-70b-versatile", messages=messages, temperature=0.8)
        rep = completion.choices[0].message.content
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR GROQ] {e}")
        return None


async def demander_ia(texte):
    state.is_thinking = True
    state.mark_user_activity()
    reg = detecter_registre(texte)
    if reg:
        noter_registre(reg)

    # ── Détection de correction : si l'utilisateur corrige, on capture
    # l'échange précédent pour apprentissage à long terme (RAG).
    _capture_correction_if_any(texte)

    await state.send_web_state("thinking")
    try:
        # ── FAST-PATH : dispatcher d'intention local ──────────────────────
        # Latence ~50 ms au lieu d'un round-trip cloud de 1–2 s pour les
        # commandes évidentes (allume X, éteins Y, heure, date, thermostat...).
        from jarvis.intent import detect as detect_intent
        intent = detect_intent(texte)
        if intent is not None:
            print(f"[INTENT] fast-path : {intent.name}")
            state.ajouter_historique("user", texte)
            state.ajouter_historique("model", intent.reply)
            return intent.reply

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
        except Exception as e:
            print(f"[IA] Gemini KO : {e} — repli sur Groq/Grok/Ollama (même prompt complet).")

        # Repli sur les LLM concurrents AVEC le prompt unifié — ils gardent la
        # personnalité de Jarvis. SerpAPI en tout dernier recours (réponse
        # générique) plutôt qu'avant Groq.
        rep_groq = await demander_groq(texte)
        if rep_groq: return rep_groq

        if grok_client:
            try:
                rep_grok = await demander_grok(texte)
                if rep_grok: return rep_grok
            except Exception: pass

        rep_ollama = await demander_ollama(texte)
        if rep_ollama: return rep_ollama

        # Ultime filet : recherche web si on a une vraie question factuelle.
        from jarvis.home import recherche_web_serpapi
        if len(texte.split()) > 2:
            res_serp = recherche_web_serpapi(texte)
            if res_serp and "VOTRE_CLE" not in res_serp and "rien trouvé" not in res_serp:
                return "Voici ce que j'ai trouvé sur le web : " + res_serp

        rep_loc = reponse_locale(texte)
        if rep_loc: return rep_loc

        return "Desole Floriace, mes serveurs sont surchargés. Je reste disponible pour vos commandes domestiques locales."
    finally:
        state.is_thinking = False
        await state.send_web_state("idle")


async def demander_ia_stream(texte, on_sentence=None):
    """Variante streaming de `demander_ia`. Appelle `on_sentence(phrase)` pour
    chaque phrase complète au fur et à mesure qu'elle arrive, permettant de
    lancer la TTS avant même que le LLM n'ait fini de générer. Suspend
    automatiquement les appels `on_sentence` dès qu'un `{` apparaît dans
    le flux (c'est alors une commande JSON : le dispatcher d'actions prendra
    le relais à la fin).

    Renvoie le texte complet accumulé. En cas d'échec du streaming, fallback
    silencieux sur `demander_ia` classique.
    """
    from jarvis.sentence_splitter import split_streaming

    state.is_thinking = True
    state.mark_user_activity()
    reg = detecter_registre(texte)
    if reg:
        noter_registre(reg)

    _capture_correction_if_any(texte)

    await state.send_web_state("thinking")

    try:
        # ── Fast-path intent local ────────────────────────────────────────
        from jarvis.intent import detect as detect_intent
        intent = detect_intent(texte)
        if intent is not None:
            print(f"[INTENT-STREAM] fast-path : {intent.name}")
            state.ajouter_historique("user", texte)
            state.ajouter_historique("model", intent.reply)
            if on_sentence and "{" not in intent.reply:
                await on_sentence(intent.reply)
            return intent.reply

        # Gemini absent → on retombe sur le non-streaming unifié.
        if not client or not types:
            rep = await demander_ia(texte)
            if on_sentence and rep and "{" not in rep:
                for s in split_streaming(rep + " ")[0]:
                    await on_sentence(s)
            return rep

        prompt_actuel = construire_system_prompt(texte)
        temp_hist = state.historique + [
            types.Content(role="user", parts=[types.Part(text=texte)])
        ]

        buffer = ""
        full = ""
        json_detected = False
        last_err = None

        for model_name in MODELS_LIST:
            try:
                def _start_stream():
                    return client.models.generate_content_stream(
                        model=model_name,
                        config=types.GenerateContentConfig(
                            system_instruction=prompt_actuel,
                            temperature=0.7,
                            tools=[types.Tool(google_search=types.GoogleSearch())],
                        ),
                        contents=temp_hist,
                    )

                stream = await asyncio.wait_for(
                    asyncio.to_thread(_start_stream), timeout=8.0
                )

                def _next(it=stream):
                    try:
                        return next(it)
                    except StopIteration:
                        return None

                while True:
                    chunk = await asyncio.wait_for(
                        asyncio.to_thread(_next), timeout=12.0
                    )
                    if chunk is None:
                        break
                    delta = getattr(chunk, "text", None) or ""
                    if not delta:
                        continue
                    full += delta

                    if json_detected:
                        continue
                    buffer += delta
                    if "{" in buffer:
                        json_detected = True
                        continue
                    sentences, buffer = split_streaming(buffer)
                    for s in sentences:
                        if on_sentence:
                            try:
                                await on_sentence(s)
                            except Exception as e:
                                print(f"[STREAM] on_sentence : {e}")

                # Flush du reliquat éventuel (phrase finale sans espace après).
                if not json_detected and buffer.strip() and on_sentence:
                    try:
                        await on_sentence(buffer.strip())
                    except Exception as e:
                        print(f"[STREAM] on_sentence flush : {e}")

                state.ajouter_historique("user", texte)
                state.ajouter_historique("model", full)
                return full
            except Exception as e:
                last_err = e
                continue

        # Tous les modèles Gemini ont raté le streaming : repli non-streaming.
        print(f"[STREAM] Gemini KO ({last_err}) — repli non-streaming.")
        rep = await demander_ia(texte)
        if on_sentence and rep and "{" not in rep:
            for s in split_streaming(rep + " ")[0]:
                await on_sentence(s)
        return rep
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
