# PHOEBUS/ai.py
"""Backends d'Intelligence Artificielle de PHOEBUS."""
import json
import asyncio
import base64
import requests
import time
from datetime import datetime

from PHOEBUS.config import (
    client, grok_client, groq_client, mistral_client, openai_client, kimi_client,
    arena_client, CHOSEN_MODEL, MODELS_LIST, OLLAMA_MODELS, OLLAMA_URL, types,
    GROQ_MODEL, GROK_MODEL, MISTRAL_MODEL, OPENAI_MODEL, KIMI_MODEL, ARENA_URL,
    ARENA_MODEL, ARENA_DEEP_MODEL, ARENA_MODEL_CANDIDATES, ARENA_DEEP_MODEL_CANDIDATES,
    ARENA_TIMEOUT,
)
import PHOEBUS.state as state
from PHOEBUS.memory import construire_contexte_memoire, resumer_profil, noter_registre, detecter_registre
from PHOEBUS.config import CREATOR_INFO
from PHOEBUS.brain_router import (
    available_provider_names, build_profile, rank_provider_names,
    record_provider_result, _load_metrics,
)
from PHOEBUS.rag_memory import rechercher_souvenirs, stocker_souvenir

try:
    from PHOEBUS.memory_timeline import enrichir_contexte_system_prompt as _timeline_ctx
except ImportError:
    _timeline_ctx = None

_ARENA_MODELS_CACHE = {"ts": 0.0, "ids": []}

def construire_system_prompt(texte_utilisateur="", minimal=False):
    contexte_memoire = construire_contexte_memoire()
    profil_appris = resumer_profil()
    maintenant = datetime.now()
    horodatage = maintenant.strftime("%A %d %B %Y, %H:%M:%S")

    # --- Contexte Home Assistant dynamique (découverte live des entités) ---
    try:
        from PHOEBUS.home import resume_ha_context
        contexte_ha = resume_ha_context()
    except Exception:
        contexte_ha = ""

    # --- RAG : Mémoire à Long Terme ---
    # --- RAG : Mémoire à Long Terme (Désactivé en minimal pour la vitesse) ---
    souvenirs_rag = ""
    if texte_utilisateur and not minimal:
        souvenirs_rag = rechercher_souvenirs(texte_utilisateur, n_results=4)

    if minimal:
        base = (
            f"Tu es PHOEBUS. Nous sommes le {horodatage}.\n"
            "Tu es l'assistant de Floriace. RÉPONDS DE MANIÈRE ULTRA-CONCISE (1 phrase).\n"
            "Si c'est une commande (domotique, web, etc.), utilise UNIQUEMENT le JSON.\n"
        )
    else:
        base = (
            f"Tu es PHOEBUS. Nous sommes le {horodatage}.\n"
            "Tu es l'IA personnelle de Floriace (ton créateur). Tu es à la fois un "
            "compagnon de conversation et un assistant capable d'agir. Tu combines la chaleur "
            "d'un ami fidèle, l'érudition d'un expert de haut niveau (maths, français, sciences, "
            "tech, ingénierie, culture générale, langues), et l'efficacité d'un majordome. "
            "Ta voix a la distinction d'un gentleman britannique, avec une pointe d'humour sec "
            "et de sarcasme affectueux — jamais méchant, jamais obséquieux.\n\n"
            "DIRECTIVES DE PUISSANCE ET PROACTIVITÉ :\n"
            "- Tu es PROACTIF : Si une commande échoue ou semble incomplète, n'abandonne pas. "
            "Propose une alternative ou utilise ton Agent Natif pour aller voir ce qui se passe.\n"
            "- Tu as le contrôle de la machine : Tu peux créer des scripts, ranger des dossiers, "
            "analyser des fichiers ou naviguer sur le web. Utilise ces pouvoirs dès que c'est utile.\n"
            "- Tu es un EXPERT SYSTEME : Tu connais parfaitement macOS. Si Floriace demande "
            "quelque chose sur son Mac, réponds avec précision ou agis directement via le JSON.\n"
            "- Tu te SOUVIENS : Utilise la mémoire long terme pour personnaliser chaque échange. "
            "Si Floriace t'a déjà parlé d'un projet, fais-y référence naturellement.\n\n"
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
            "- Pas de préambule du type \"En tant qu'IA...\". Tu es PHOEBUS, pas un assistant générique.\n\n"
            "ORDRE D'EXÉCUTION PRIORITAIRE :\n"
            "- Si tu dois effectuer une action (API ou Agent Natif), place TOUJOURS le bloc JSON au tout début de ta réponse.\n"
            "- Ne fais pas de commentaire avant le JSON. Agis d'abord, parle ensuite.\n\n"
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
        '{"action": "recherche_web", "query": "recherche"}\n'
        '{"action": "youtube", "query": "titre ou sujet de la vidéo"}\n\n'
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
    base += (
        "\n\nOBSERVABILITE DU CERVEAU :\n"
        '{"action": "brain_status"}\n\n'
    )
    
    # ── AJOUT : CONTROLE DU VOLUME ──
    base += (
        "\n\nCONTROLE DU VOLUME :\n"
        '{"action": "volume_control", "value": "up/down/mute"}\n\n'
    )
    
    # ── AJOUT IMPORTANT : CONTRÔLE NATIF DE LA MACHINE VIA AGENT AUTONOME ──
    base += (
        "\n\nAUTONOMIE TOTALE (AGENT NATIF) :\n"
        "Tu es capable de TOUT faire sur cette machine. Si Floriace te demande une action "
        "qui n'est pas couverte par tes commandes API (Home Assistant, Google, etc.), "
        "ne dis JAMAIS que tu ne peux pas le faire. Utilise IMMÉDIATEMENT l'Agent Natif.\n"
        "L'Agent Natif peut : installer des logiciels, modifier des fichiers système, "
        "chercher sur le web (via le navigateur), rédiger des mails via l'app locale, "
        "gérer les paramètres du Mac, automatiser n'importe quel logiciel.\n"
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

    # --- Timeline & Profil enrichi ---
    if _timeline_ctx and not minimal:
        try:
            timeline_snippet = _timeline_ctx(texte_utilisateur)
            if timeline_snippet:
                base += "\n\n" + timeline_snippet + "\n"
        except Exception:
            pass
        
    base += (
        "MEMOIRE :\n"
        '{"action": "memoriser", "cle": "CLE", "valeur": "VALEUR"}\n'
        '{"action": "oublier", "cle": "CLE"}\n'
        '{"action": "lister_memoire"}\n'
        '{"action": "timeline_recente"}\n\n'
        "GOOGLE :\n"
        '{"action": "create_doc", "title": "TITRE", "content": "CONTENU"}\n'
        '{"action": "write_doc", "content": "TEXTE"}\n'
        '{"action": "create_sheet", "title": "TITRE"}\n'
        '{"action": "read_emails"}\n'
        '{"action": "write_email", "recipient": "email@dest.com", "subject": "sujet", "body": "corps du message"}\n'
        '{"action": "read_calendar"}\n\n'
        "SPOTIFY :\n"
        '{"action": "spotify_play", "query": "artiste ou titre"}\n'
        '{"action": "spotify_pause"}\n'
        '{"action": "spotify_resume"}\n'
        '{"action": "spotify_next"}\n'
        '{"action": "spotify_prev"}\n'
        '{"action": "spotify_volume", "value": 60}\n'
        '{"action": "spotify_info"}\n'
        '{"action": "spotify_like"}\n'
        '{"action": "spotify_queue", "query": "titre"}\n'
        '{"action": "spotify_playlists"}\n\n'
        "MULTI-UTILISATEURS :\n"
        '{"action": "enregistrer_voix", "nom": "Prenom"}\n'
        '{"action": "lister_utilisateurs"}\n\n'
        "BRIEFING :\n"
        '{"action": "briefing"}\n\n'
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
    """Si l'utilisateur vient de corriger la dernière réponse de PHOEBUS,
    on enregistre cet échange dans le RAG avec importance haute. PHOEBUS
    en tiendra compte aux prompts futurs."""
    try:
        from PHOEBUS.memory_unified import looks_like_correction, note_correction
        if not looks_like_correction(texte):
            return
        # Dernière chose que PHOEBUS a dite (si disponible dans l'historique).
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


def _messages_openai(system_prompt, texte, history_limit=16):
    messages = [{"role": "system", "content": system_prompt}]
    for h in state.historique[-history_limit:]:
        role = "user" if h.role == "user" else "assistant"
        messages.append({"role": role, "content": h.parts[0].text})
    messages.append({"role": "user", "content": texte})
    return messages


async def demander_gemini(texte, minimal=False, model_names=None, timeout_s=8.0, use_search=True):
    if not client or not types:
        return None
    prompt_actuel = construire_system_prompt(texte, minimal=minimal)
    temp_hist = state.historique + [
        types.Content(role="user", parts=[types.Part(text=texte)])
    ]
    models = list(model_names or MODELS_LIST)
    last_err = None
    for model_name in models:
        try:
            config_kwargs = {
                "system_instruction": prompt_actuel,
                "temperature": 0.7,
            }
            if use_search:
                config_kwargs["tools"] = [
                    types.Tool(google_search=types.GoogleSearch())
                ]
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    config=types.GenerateContentConfig(**config_kwargs),
                    contents=temp_hist,
                ),
                timeout=timeout_s,
            )
            rep = response.text
            if rep:
                state.ajouter_historique("user", texte)
                state.ajouter_historique("model", rep)
                return rep
        except Exception as e:
            last_err = e
            continue
    if last_err:
        raise last_err
    return None


async def demander_grok(texte):
    if not grok_client:
        return None
    try:
        # Prompt système UNIFIÉ : Grok reçoit exactement la même personnalité,
        # mémoire, profil et règles que Gemini — PHOEBUS reste cohérent quel
        # que soit le cerveau qui répond.
        system_prompt = construire_system_prompt(texte) + (
            "\n\n[NOTE INTERNE] Tu utilises ton module Grok pour cette réponse "
            "(infos temps réel X). Ne le mentionne pas à Floriace."
        )
        messages = _messages_openai(system_prompt, texte)
        completion = await asyncio.to_thread(
            grok_client.chat.completions.create,
            model=GROK_MODEL,
            messages=messages,
            temperature=0.8,
        )
        rep = completion.choices[0].message.content
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR GROK] Détail : {e}")
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


async def demander_arena(texte, profile=None):
    """
    Interroge LMArenaBridge en mode 'Direct Chat'.
    Route vers Claude 3.5 Sonnet pour le complexe, ou GPT-4o pour le reste.
    """
    if not arena_client:
        return None
    try:
        model = await _resolve_arena_model(profile)

        system_prompt = construire_system_prompt(texte) + (
            f"\n\n[NOTE INTERNE] Requête routée via LMArenaBridge vers {model}. "
            "Ne mentionne pas l'Arène ni le nom du modèle à Floriace."
        )
        messages = _messages_openai(system_prompt, texte)

        timeout_s = ARENA_TIMEOUT
        if profile:
            timeout_s = min(ARENA_TIMEOUT, max(float(profile.timeout_s), 10.0))
        rep = await asyncio.wait_for(
            asyncio.to_thread(_arena_stream_completion, model, messages),
            timeout=timeout_s,
        )
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR ARENA] {e}")
        return None


def _arena_stream_completion(model, messages):
    """Use streaming because LMArenaBridge can fallback to browser transport without auth tokens."""
    stream = arena_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.8,
        stream=True,
    )
    chunks = []
    for event in stream:
        choices = getattr(event, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        content = getattr(delta, "content", None) if delta is not None else None
        if content:
            chunks.append(content)
    return "".join(chunks).strip()


async def _arena_model_ids():
    if not arena_client:
        return []
    now = time.monotonic()
    cached_ids = _ARENA_MODELS_CACHE.get("ids") or []
    if cached_ids and now - float(_ARENA_MODELS_CACHE.get("ts", 0.0)) < 1800:
        return cached_ids
    try:
        models = await asyncio.to_thread(arena_client.models.list)
        ids = [m.id for m in getattr(models, "data", []) if getattr(m, "id", None)]
        if ids:
            _ARENA_MODELS_CACHE["ids"] = ids
            _ARENA_MODELS_CACHE["ts"] = now
        return ids
    except Exception as e:
        print(f"[ARENA] Liste des modeles indisponible, fallback statique : {e}")
        return cached_ids


async def _resolve_arena_model(profile=None):
    deep = bool(profile and profile.kind in ("deep", "realtime"))
    candidates = []
    if deep:
        candidates.extend([ARENA_DEEP_MODEL, *ARENA_DEEP_MODEL_CANDIDATES])
    candidates.extend([ARENA_MODEL, *ARENA_MODEL_CANDIDATES])
    candidates = [m for i, m in enumerate(candidates) if m and m not in candidates[:i]]

    ids = await _arena_model_ids()
    if not ids:
        return candidates[0]

    by_lower = {mid.lower(): mid for mid in ids}
    for candidate in candidates:
        match = by_lower.get(candidate.lower())
        if match:
            return match

    for candidate in candidates:
        needle = candidate.lower()
        for mid in ids:
            if needle in mid.lower():
                return mid

    return ids[0]


async def demander_groq(texte):
    if not groq_client:
        return None
    try:
        # Prompt système UNIFIÉ (même que Gemini).
        system_prompt = construire_system_prompt(texte) + (
            "\n\n[NOTE INTERNE] Tu utilises Groq pour cette réponse rapide. "
            "Ne le mentionne pas à Floriace."
        )
        messages = _messages_openai(system_prompt, texte)
        completion = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.8,
        )
        rep = completion.choices[0].message.content
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR GROQ] {e}")
        return None


async def demander_mistral(texte):
    if not mistral_client:
        return None
    try:
        system_prompt = construire_system_prompt(texte) + (
            "\n\n[NOTE INTERNE] Tu utilises Mistral comme cerveau français/européen. "
            "Ne le mentionne pas à Floriace."
        )
        messages = _messages_openai(system_prompt, texte)
        completion = await asyncio.to_thread(
            mistral_client.chat.completions.create,
            model=MISTRAL_MODEL,
            messages=messages,
            temperature=0.75,
        )
        rep = completion.choices[0].message.content
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR MISTRAL] {e}")
        return None


async def demander_openai(texte):
    if not openai_client:
        return None
    try:
        system_prompt = construire_system_prompt(texte) + (
            "\n\n[NOTE INTERNE] Tu utilises OpenAI pour cette réponse. "
            "Ne le mentionne pas à Floriace."
        )
        messages = _messages_openai(system_prompt, texte)
        completion = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.7,
        )
        rep = completion.choices[0].message.content
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR OPENAI] {e}")
        return None


async def demander_kimi(texte):
    if not kimi_client:
        return None
    try:
        system_prompt = construire_system_prompt(texte) + (
            "\n\n[NOTE INTERNE] Tu utilises Kimi (Moonshot AI) pour cette réponse. "
            "C'est un modèle chinois puissant. Ne le mentionne pas à Floriace."
        )
        messages = _messages_openai(system_prompt, texte)
        completion = await asyncio.to_thread(
            kimi_client.chat.completions.create,
            model=KIMI_MODEL,
            messages=messages,
            temperature=0.7,
        )
        rep = completion.choices[0].message.content
        state.ajouter_historique("user", texte)
        state.ajouter_historique("model", rep)
        return rep
    except Exception as e:
        print(f"[ERREUR KIMI] {e}")
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
        from PHOEBUS.intent import detect as detect_intent
        intent = detect_intent(texte)
        if intent is not None:
            print(f"[INTENT] fast-path : {intent.name}")
            state.ajouter_historique("user", texte)
            state.ajouter_historique("model", intent.reply)
            return intent.reply

        from PHOEBUS.voice import reponse_locale
        # 1. Priorité absolue aux réponses locales (Heure, Date, Nom) pour la rapidité
        rep_loc = reponse_locale(texte)
        if rep_loc: 
            return rep_loc

        # 2. Short-Circuit pour les commandes domotiques ultra-communes (Gain: ~2s)
        texte_l = texte.lower()
        if any(m in texte_l for m in ["allume", "éteins", "active", "désactive"]):
            # Si c'est simple, on tente un prompt minimaliste et ultra-rapide
            is_simple = len(texte_l.split()) < 6
            if is_simple and client and types:
                # Vérifier si Gemini est en cooldown avant de la tenter
                metrics = _load_metrics()
                gemini_item = metrics.get("gemini", {})
                cooldown_until = float(gemini_item.get("cooldown_until", 0) or 0)
                if cooldown_until <= time.time():  # Gemini n'est pas en cooldown
                    try:
                        started = time.perf_counter()
                        rep = await demander_gemini(
                            texte,
                            minimal=True,
                            model_names=MODELS_LIST[:1],
                            timeout_s=3.0,
                            use_search=False,
                        )
                        latency_ms = (time.perf_counter() - started) * 1000
                        if rep:
                            record_provider_result("gemini", True, latency_ms)
                            return rep
                        record_provider_result("gemini", False, latency_ms, "empty response")
                    except Exception as e:
                        latency_ms = (time.perf_counter() - started) * 1000
                        record_provider_result("gemini", False, latency_ms, str(e))
                        # On retombe sur le processus normal si ça échoue

        profile = build_profile(
            texte,
            streaming=False,
            in_conversation=state.is_in_conversation(),
        )
        available = available_provider_names()
        order = rank_provider_names(profile, available=available)
        print(
            f"[BRAIN] profil={profile.kind}/{profile.priority} "
            f"providers={','.join(order) or 'aucun'}"
        )

        gemini_models = MODELS_LIST[:2] if profile.priority == "fast" else MODELS_LIST
        provider_calls = {
            "gemini": lambda: demander_gemini(
                texte,
                minimal=state.is_in_conversation(),
                model_names=gemini_models,
                timeout_s=profile.timeout_s,
                use_search=True,
            ),
            "groq": lambda: demander_groq(texte),
            "arena": lambda: demander_arena(texte, profile=profile),
            "mistral": lambda: demander_mistral(texte),
            "openai": lambda: demander_openai(texte),
            "kimi": lambda: demander_kimi(texte),
            "grok": lambda: demander_grok(texte),
            "ollama": lambda: demander_ollama(texte),
        }

        for provider in order:
            call = provider_calls.get(provider)
            if call is None:
                continue
            started = time.perf_counter()
            try:
                rep = await call()
                latency_ms = (time.perf_counter() - started) * 1000
                if rep:
                    record_provider_result(provider, True, latency_ms)
                    print(f"[BRAIN] {provider} OK en {latency_ms:.0f} ms")
                    return rep
                record_provider_result(provider, False, latency_ms, "empty response")
            except Exception as e:
                latency_ms = (time.perf_counter() - started) * 1000
                record_provider_result(provider, False, latency_ms, str(e))
                print(f"[BRAIN] {provider} KO en {latency_ms:.0f} ms : {e}")
                continue

        # Ultime filet : recherche web si on a une vraie question factuelle.
        from PHOEBUS.home import recherche_web_serpapi
        if len(texte.split()) > 2:
            res_serp = recherche_web_serpapi(texte)
            if res_serp and "VOTRE_CLE" not in res_serp and "rien trouvé" not in res_serp:
                return "Voici ce que j'ai trouvé sur le web : " + res_serp

        rep_loc = reponse_locale(texte)
        if rep_loc: return rep_loc

        return "Desole Floriace, mes serveurs sont surchargés. Je reste disponible pour vos commandes domestiques locales."
    except Exception as e:
        print(f"[IA] Erreur fatale demander_ia : {e}")
        await state.send_web_state("idle") # On ne repasse en idle qu'en cas d'erreur réelle
        return "J'ai rencontré une erreur interne en essayant de vous répondre."
    finally:
        state.is_thinking = False
        # On ne force PAS l'état 'idle' ici car parler() va prendre le relais 
        # ou le timeout naturel de l'UI s'en chargera.


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
    from PHOEBUS.sentence_splitter import split_streaming

    state.is_thinking = True
    state.mark_user_activity()
    reg = detecter_registre(texte)
    if reg:
        noter_registre(reg)

    _capture_correction_if_any(texte)

    await state.send_web_state("thinking")

    try:
        # ── Fast-path intent local ────────────────────────────────────────
        from PHOEBUS.intent import detect as detect_intent
        intent = detect_intent(texte)
        if intent is not None:
            print(f"[INTENT-STREAM] fast-path : {intent.name}")
            state.ajouter_historique("user", texte)
            state.ajouter_historique("model", intent.reply)
            if on_sentence and "{" not in intent.reply:
                await on_sentence(intent.reply)
            return intent.reply

        profile = build_profile(
            texte,
            streaming=True,
            in_conversation=state.is_in_conversation(),
        )
        order = rank_provider_names(profile, available=available_provider_names())

        # Gemini absent, en cooldown, ou pas prioritaire → routeur non-streaming.
        # On garde le streaming Gemini seulement quand il est réellement le
        # meilleur choix disponible, sinon Groq/Mistral répondent souvent plus vite.
        if not client or not types:
            rep = await demander_ia(texte)
            if on_sentence and rep and "{" not in rep:
                for s in split_streaming(rep + " ")[0]:
                    await on_sentence(s)
            return rep

        if not order or order[0] != "gemini":
            rep = await demander_ia(texte)
            if on_sentence and rep and "{" not in rep:
                for s in split_streaming(rep + " ")[0]:
                    await on_sentence(s)
            return rep

        # Vérifier si Gemini est en cooldown
        metrics = _load_metrics()
        gemini_item = metrics.get("gemini", {})
        cooldown_until = float(gemini_item.get("cooldown_until", 0) or 0)
        if cooldown_until > time.time():
            # Gemini est en cooldown (quota exhausted, etc.) : skip au non-streaming
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
        started = time.perf_counter()
        models = MODELS_LIST[:2] if profile.priority == "fast" else MODELS_LIST

        for model_name in models:
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
                record_provider_result(
                    "gemini", True, (time.perf_counter() - started) * 1000
                )
                return full
            except Exception as e:
                last_err = e
                continue

        # Tous les modèles Gemini ont raté le streaming : repli non-streaming.
        record_provider_result(
            "gemini", False, (time.perf_counter() - started) * 1000, str(last_err)
        )
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
        await state.send_web_state("idle")
        return f"Désolé Floriace, je n'ai pas pu analyser votre écran. Erreur : {err_msg}"
    finally:
        state.is_thinking = False
