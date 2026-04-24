# PHOEBUS/actions.py
"""Dispatcher central de PHOEBUS. Traite les réponses JSON de l'IA."""
import asyncio
import json

import PHOEBUS.state as state
from PHOEBUS.security import audit_log, is_sensitive_action, describe_action, risk_level_for
from PHOEBUS.home import (
    resolve_ha_entity, ha_lumiere, ha_interrupteur, ha_thermostat, ha_scene,
    resolve_temperature_sensor, resolve_humidity_sensor, resolve_battery_sensor,
    resolve_energy_sensor, resolve_alarm_entity, resolve_vacuum_entity,
    resolve_scene_entity,
    ha_get_etat, ha_appeler_service, ha_get_calendrier, get_meteo_actuelle,
    get_alertes_meteo, get_resultats_football, get_classement_football, get_resultats_sport_gemini,
    recherche_web_serpapi, PIECES_LUMIERES, PIECES_PRISES,
    HA_TARIFS
)
from PHOEBUS.memory import ajouter_memoire, supprimer_memoire, charger_memoire, apprendre_signal
from PHOEBUS.rag_memory import stocker_souvenir
from PHOEBUS.utils import normalize_text
from PHOEBUS.desktop import (
    ouvrir_dossier, lister_dossier, trier_par_type, trier_par_date,
    trier_par_type_puis_date, creer_sous_dossier, renommer_fichier,
    deplacer_fichier, chercher_fichier, action_whatsapp_appel
)
from PHOEBUS.google_services import (
    creer_google_doc, modifier_google_doc, lire_emails, lister_evenements_calendar,
    creer_google_sheet, envoyer_email
)
from PHOEBUS.vision import PHOEBUS_vision_cliquer, PHOEBUS_vision_ecrire
from PHOEBUS.agent import orchestrer_agent_autonome
from PHOEBUS.voice import parler
from PHOEBUS.skills import get_skill, describe_skill

# Imports optionnels des nouveaux modules
try:
    from PHOEBUS import spotify as _spotify
    _SPOTIFY_AVAILABLE = True
except ImportError:
    _SPOTIFY_AVAILABLE = False

try:
    from PHOEBUS.memory_timeline import enregistrer_evenement as _timeline_evt
except ImportError:
    _timeline_evt = None


async def _executer_en_fond(handler, data, label):
    """Exécute un handler en tâche asyncio séparée pour ne pas bloquer la conversation."""
    async def _run():
        try:
            await handler(data)
        except Exception as e:
            print(f"[BG:{label}] erreur : {e}")
    task = asyncio.create_task(_run())
    state.register_background_task(task, label=label)


async def executer_une_action(d):
    """Exécute un bloc JSON unique."""
    action = d.get("action")
    if not action:
        return

    # ── Dispatch via le registre de skills (prioritaire) ──────────────────────
    sk = get_skill(action)
    if sk:
        try:
            if sk.background:
                await _executer_en_fond(sk.handler, d, label=sk.name)
            else:
                await sk.handler(d)
        except Exception as e:
            print(f"[SKILL:{action}] erreur : {e}")
            await parler(f"J'ai eu un pépin en exécutant {action}.")
        return

    # ── AGENT NATIF ── (tourne en tâche de fond : la conversation continue) ──
    if action == "agent_natif":
        instruction = d.get("instruction", "")
        await parler(f"J'initie l'agent autonome pour : {instruction}")

        async def _run_agent():
            res = await orchestrer_agent_autonome(instruction)
            await parler(f"Tâche autonome terminée : {res}")

        task = asyncio.create_task(_run_agent())
        state.register_background_task(task, label=f"agent_natif: {instruction[:60]}")
        return

    # ── DOSSIERS & FICHIERS ──────────────────────────────────────────────────
    if action == "ouvrir_dossier":
        chemin = d.get("chemin", "bureau")
        ok, msg = ouvrir_dossier(chemin)
        await parler(f"C'est fait Floriace. Dossier {chemin} ouvert." if ok else msg)
        return
        
    elif action == "lister_dossier":
        res, msg = lister_dossier()
        if msg: await parler(msg)
        else:
            f = len(res['fichiers'])
            dd = len(res['dossiers'])
            await parler(f"Ce dossier contient {f} fichiers et {dd} sous-dossiers.")
        return
        
    elif action == "trier_par_type":
        ok, msg = trier_par_type()
        await parler(msg)
        return
        
    elif action == "trier_par_date":
        ok, msg = trier_par_date()
        await parler(msg)
        return
        
    elif action == "trier_complet":
        ok, msg = trier_par_type_puis_date()
        await parler(msg)
        return
        
    elif action == "creer_dossier":
        nom = d.get("nom")
        if nom:
            ok, msg = creer_sous_dossier(nom)
            await parler(msg)
        return
        
    elif action == "renommer_fichier":
        a = d.get("ancien")
        n = d.get("nouveau")
        if a and n:
            ok, msg = renommer_fichier(a, n)
            await parler(msg)
        return
        
    elif action == "deplacer_fichier":
        f = d.get("fichier")
        dest = d.get("destination")
        if f and dest:
            ok, msg = deplacer_fichier(f, dest)
            await parler(msg)
        return
        
    elif action == "chercher_fichier":
        n = d.get("nom")
        if n:
            res, msg = chercher_fichier(n)
            if msg: await parler(msg)
            elif res: await parler(f"J'ai trouvé {len(res)} fichiers correspondants.")
            else: await parler("Aucun fichier trouvé.")
        return

    # ── HOME ASSISTANT ────────────────────────────────────────────────────────
    elif action == "ha_lumiere":
        p = d.get("piece", "salon")
        e = d.get("etat", "on")
        c = d.get("couleur")
        l = d.get("luminosite")

        ent = resolve_ha_entity("light", p, PIECES_LUMIERES, default_prefix="light")
        if ha_lumiere(ent, e, luminosite=l):
            apprendre_signal(f"piece:{p}")
            await parler(f"Lumière {e} dans {p}.")
        else:
            await parler("Impossible de contrôler la lumière.")
        return
        
    elif action == "ha_prise":
        p = d.get("piece", "salon")
        e = d.get("etat", "on")
        ent = resolve_ha_entity("switch", p, PIECES_PRISES, default_prefix="switch")
        if ha_interrupteur(ent, e):
            await parler(f"Prise {e} pour {p}.")
        else:
            await parler("Impossible de contrôler la prise.")
        return
        
    elif action == "ha_temperature":
        p = d.get("piece", "salon")
        ent = resolve_temperature_sensor(p)
        val = ha_get_etat(ent)
        if val != "inconnu":
            await parler(f"Il fait {val} degrés dans {p}.")
        else:
            await parler("Capteur de température introuvable.")
        return
        
    elif action == "ha_humidite":
        p = d.get("piece", "salon")
        ent = resolve_humidity_sensor(p)
        val = ha_get_etat(ent)
        if val != "inconnu":
            await parler(f"Le taux d'humidité dans {p} est de {val}%.")
        else:
            await parler("Capteur d'humidité introuvable.")
        return
        
    elif action == "ha_batterie":
        a = d.get("appareil", "mon téléphone")
        ent = resolve_battery_sensor(a)
        val = ha_get_etat(ent)
        if val != "inconnu":
            await parler(f"La batterie de {a} est à {val}%.")
        else:
            await parler("Impossible de trouver la batterie.")
        return
        
    elif action == "ha_energie":
        a = d.get("appareil", "tv")
        p = d.get("periode", "mois")
        ent = resolve_energy_sensor(a)
        val = ha_get_etat(ent)
        if val != "inconnu":
            try:
                kwh = float(val)
                cout = round(kwh * HA_TARIFS["p1"], 2)
                await parler(f"La consommation est de {kwh} kWh, soit environ {cout} euros.")
            except ValueError:
                await parler(f"La consommation est de {val} kWh.")
        else:
            await parler("Capteur d'énergie introuvable.")
        return
        
    elif action == "ha_alarme":
        e = d.get("etat", "on")
        ent = resolve_alarm_entity()
        srv = "alarm_arm_away" if e == "on" else "alarm_disarm"
        if ha_appeler_service("alarm_control_panel", srv, ent):
            await parler(f"Alarme {e}.")
        else:
            await parler("Erreur avec l'alarme.")
        return
        
    elif action == "ha_thermostat":
        t = d.get("temperature", 20)
        ent = resolve_ha_entity("climate", "salon")
        if ha_thermostat(ent, t):
            await parler(f"Thermostat réglé sur {t} degrés.")
        else:
            await parler("Impossible de régler le thermostat.")
        return
        
    elif action == "ha_scene":
        n = d.get("nom", "")
        ent = resolve_scene_entity(n)
        if ha_scene(ent):
            await parler(f"Scène {n} activée.")
        else:
            await parler(f"Impossible de lancer la scène {n}.")
        return

    elif action == "ha_aspirateur":
        cmd = d.get("commande", "start").lower()
        ent = resolve_vacuum_entity()
        srv_map = {
            "start": "start", "demarre": "start", "nettoie": "start",
            "stop": "stop", "arrete": "stop",
            "pause": "pause",
            "base": "return_to_base", "rentre": "return_to_base"
        }
        srv = srv_map.get(cmd, "start")
        if ha_appeler_service("vacuum", srv, ent):
            await parler(f"Ordre {cmd} envoyé à l'aspirateur.")
        else:
            await parler("Impossible de contrôler l'aspirateur.")
        return

    # ── WEB & METEO ──────────────────────────────────────────────────────────
    elif action == "meteo":
        v = d.get("ville", None)
        await parler(get_meteo_actuelle(v))
        return
        
    elif action == "alerte_meteo":
        v = d.get("ville", None)
        await parler(get_alertes_meteo(v))
        return
        
    elif action == "recherche_web":
        q = d.get("query", "")
        if q:
            await parler(recherche_web_serpapi(q))
        return

    elif action == "youtube":
        q = d.get("query", "")
        if q:
            from PHOEBUS.home import chercher_youtube
            from PHOEBUS.utils import open_uri
            url = chercher_youtube(q)
            if url:
                await parler(f"Je lance la vidéo sur YouTube pour : {q}.")
                open_uri(url)
            else:
                await parler("Je n'ai pas trouvé de vidéo correspondante sur YouTube.")
        return

    elif action == "volume_control":
        val = d.get("value", "up").lower()
        from PHOEBUS.config import pyautogui
        if not pyautogui:
            await parler("Le contrôle du volume n'est pas disponible sur cette machine.")
            return
        if val == "up":
            for _ in range(5): pyautogui.press('volumeup')
            await parler("Volume augmenté.")
        elif val == "down":
            for _ in range(5): pyautogui.press('volumedown')
            await parler("Volume baissé.")
        elif val == "mute":
            pyautogui.press('volumemute')
            await parler("Son coupé.")
        return

    # ── SPORT ────────────────────────────────────────────────────────────────
    elif action == "sport_resultats":
        eq = d.get("equipe")
        lig = d.get("ligue")
        await parler(get_resultats_football(equipe=eq, ligue=lig))
        return
        
    elif action == "sport_classement":
        lig = d.get("ligue")
        await parler(get_classement_football(ligue=lig))
        return
        
    elif action == "sport_live":
        q = d.get("question", "")
        await parler(get_resultats_sport_gemini(q))
        return

    # ── MEMOIRE ──────────────────────────────────────────────────────────────
    elif action == "memoriser":
        cle = d.get("cle")
        val = d.get("valeur")
        if cle and val:
            ajouter_memoire(cle, val)
            await parler(f"C'est noté, {cle} : {val}.")
        return
        
    elif action == "oublier":
        cle = d.get("cle")
        if cle:
            if supprimer_memoire(cle): await parler(f"J'ai effacé la note concernant {cle}.")
            else: await parler("Je ne trouve pas cette information en mémoire.")
        return
        
    elif action == "lister_memoire":
        m = charger_memoire()
        if m:
            txt = "Voici ce dont je me souviens : " + ", ".join([f"{k} est {v['valeur']}" for k,v in m.items()])
            await parler(txt)
        else:
            await parler("Ma mémoire est vide pour l'instant.")
        return

    # ── GOOGLE SERVICES ──────────────────────────────────────────────────────
    elif action == "create_doc":
        titre = d.get("title", "Nouveau Document")
        contenu = d.get("content", "")
        await parler(creer_google_doc(titre, contenu))
        return
        
    elif action == "write_doc":
        contenu = d.get("content", "")
        await parler(modifier_google_doc(contenu))
        return
        
    elif action == "create_sheet":
        titre = d.get("title", "Nouvelle Feuille")
        await parler(creer_google_sheet(titre))
        return
        
    elif action == "read_emails":
        await parler(lire_emails())
        return

    elif action == "write_email":
        dest = d.get("recipient")
        subj = d.get("subject", "Message de PHOEBUS")
        body = d.get("body", "")
        if dest and body:
            await parler(envoyer_email(dest, subj, body))
        else:
            await parler("Il me manque le destinataire ou le corps du message pour envoyer l'email.")
        return
        
    elif action == "read_calendar":
        await parler(lister_evenements_calendar())
        return

    # ── SPOTIFY ───────────────────────────────────────────────────────────────
    elif action == "spotify_play":
        q = d.get("query", "")
        if _SPOTIFY_AVAILABLE and q:
            await parler(await asyncio.to_thread(_spotify.jouer, q))
        elif not _SPOTIFY_AVAILABLE:
            await parler("Le module Spotify n'est pas installé. Lancez pip install spotipy.")
        return

    elif action == "spotify_pause":
        if _SPOTIFY_AVAILABLE:
            await parler(await asyncio.to_thread(_spotify.pause))
        return

    elif action == "spotify_resume":
        if _SPOTIFY_AVAILABLE:
            await parler(await asyncio.to_thread(_spotify.reprendre))
        return

    elif action == "spotify_next":
        if _SPOTIFY_AVAILABLE:
            await parler(await asyncio.to_thread(_spotify.suivant))
        return

    elif action == "spotify_prev":
        if _SPOTIFY_AVAILABLE:
            await parler(await asyncio.to_thread(_spotify.precedent))
        return

    elif action == "spotify_volume":
        niveau = int(d.get("value", 50))
        if _SPOTIFY_AVAILABLE:
            await parler(await asyncio.to_thread(_spotify.volume, niveau))
        return

    elif action == "spotify_info":
        if _SPOTIFY_AVAILABLE:
            info = await asyncio.to_thread(_spotify.info_lecture_en_cours)
            if info:
                await parler(
                    f"En ce moment : '{info['titre']}' de {info['artiste']}, "
                    f"album {info['album']}."
                )
            else:
                await parler("Aucune lecture en cours sur Spotify.")
        return

    elif action == "spotify_like":
        if _SPOTIFY_AVAILABLE:
            await parler(await asyncio.to_thread(_spotify.liker_morceau_actuel))
        return

    elif action == "spotify_queue":
        q = d.get("query", "")
        if _SPOTIFY_AVAILABLE and q:
            await parler(await asyncio.to_thread(_spotify.mettre_dans_file, q))
        return

    elif action == "spotify_playlists":
        if _SPOTIFY_AVAILABLE:
            await parler(await asyncio.to_thread(_spotify.lister_playlists))
        return

    # ── MULTI-UTILISATEURS ────────────────────────────────────────────────────
    elif action == "enregistrer_voix":
        nom = d.get("nom", "")
        if nom:
            await parler(
                f"Je vais enregistrer la voix de {nom}. "
                "Parlez pendant 5 secondes s'il vous plaît."
            )
        else:
            await parler("Pour quel nom souhaitez-vous enregistrer une voix ?")
        return

    elif action == "lister_utilisateurs":
        try:
            from PHOEBUS.multi_user import lister_utilisateurs
            users = lister_utilisateurs()
            if users:
                await parler(f"Profils vocaux enregistrés : {', '.join(users)}.")
            else:
                await parler("Aucun profil vocal enregistré pour l'instant.")
        except Exception as e:
            await parler(f"Erreur multi-utilisateur : {e}")
        return

    # ── BRIEFING ──────────────────────────────────────────────────────────────
    elif action == "briefing":
        try:
            from PHOEBUS.briefing import generer_briefing
            texte = await generer_briefing()
            await parler(texte)
        except Exception as e:
            await parler(f"Impossible de générer le briefing : {e}")
        return

    # ── MÉMOIRE TIMELINE ──────────────────────────────────────────────────────
    elif action == "timeline_recente":
        try:
            from PHOEBUS.memory_timeline import get_evenements_recents
            evts = get_evenements_recents(10)
            if evts:
                resume = " | ".join(
                    f"{e['ts'][5:16]} {e['contenu'][:50]}" for e in evts[-5:]
                )
                await parler(f"Voici les événements récents : {resume}")
            else:
                await parler("Aucun événement dans la timeline pour l'instant.")
        except Exception as e:
            await parler(f"Erreur timeline : {e}")
        return

    # ── SYSTEME ──────────────────────────────────────────────────────────────
    elif action == "mode_iron_man":
        e = d.get("etat", "on")
        state.MODE_IRON_MAN = (e == "on")
        await parler("Mode Iron Man activé." if state.MODE_IRON_MAN else "Mode Iron Man désactivé.")
        return

    elif action == "brain_status":
        from PHOEBUS.brain_router import router_status
        status = router_status()
        disponibles = ", ".join(status.get("available") or []) or "aucun"
        ordre = ", ".join(status.get("order") or []) or "non configuré"
        await parler(
            f"Cerveau en mode {status.get('mode')}. "
            f"Disponibles : {disponibles}. Ordre préféré : {ordre}."
        )
        return

    # ── WHATSAPP ─────────────────────────────────────────────────────────────
    elif action == "whatsapp_appel":
        c = d.get("contact", "")
        if c:
            await action_whatsapp_appel(c, parler)
        return

    # ── VISION WEBSOCKET ─────────────────────────────────────────────────────
    elif action == "voir_ecran":
        ins = d.get("instruction", "")
        if ins:
            await parler(await PHOEBUS_vision_cliquer(ins))
        return
        
    elif action == "vision_ecrire":
        ins = d.get("instruction", "")
        txt = d.get("texte", "")
        if ins and txt:
            await parler(await PHOEBUS_vision_ecrire(ins, txt))
        return


async def traiter_reponse_ia(reponse):
    if reponse is None:
        print("[PHOEBUS] Réponse IA vide (None).")
        return False

    try:
        if state.PENDING_CONFIRMATION:
            from PHOEBUS.security import is_confirmation_text, is_cancellation_text
            
            if is_confirmation_text(reponse):
                await parler("Action confirmée, Floriace. J'exécute.")
                d = state.PENDING_CONFIRMATION
                state.PENDING_CONFIRMATION = None
                audit_log("sensitive_action_confirmed", action=d.get("action"))
                await executer_une_action(d)
                return True
                
            elif is_cancellation_text(reponse):
                await parler("Action annulée, Monsieur.")
                audit_log("sensitive_action_cancelled", action=state.PENDING_CONFIRMATION.get("action"))
                state.PENDING_CONFIRMATION = None
                return True
                
            else:
                await parler("En attente de votre confirmation. Dites 'PHOEBUS je confirme' ou 'Annule'.")
                return True

        if "{" in reponse and "}" in reponse:
            # Sauvegarder dans RAG (mémoire long terme) que PHOEBUS a fait une action structurée
            stocker_souvenir(f"Action JSON demandée : {reponse}", source="system", importance=2)
            
            parties = []
            texte_restant = reponse
            while "{" in texte_restant and "}" in texte_restant:
                debut = texte_restant.find("{")
                fin = texte_restant.find("}") + 1
                try:
                    d = json.loads(texte_restant[debut:fin])
                    parties.append(d)
                except json.JSONDecodeError:
                    pass
                texte_restant = texte_restant[fin:]

            if parties:
                for d in parties:
                    action = d.get("action", "")
                    risk = risk_level_for(action)
                    desc = describe_skill(d) or describe_action(d)

                    if risk == "high":
                        await parler(f"Vous me demandez de {desc}. C'est une action sensible, vous confirmez ?")
                        state.PENDING_CONFIRMATION = d
                        audit_log("sensitive_action_pending", action=action, description=desc, risk=risk)
                        return True

                    if risk == "medium":
                        # Annonce + courte fenêtre pour barge-in avant l'exécution.
                        await parler(f"J'applique : {desc}.")
                        await asyncio.sleep(1.2)
                        if state.STOP_PARLER:
                            state.STOP_PARLER = False
                            await parler("D'accord, j'annule.")
                            audit_log("medium_action_aborted", action=action, description=desc)
                            continue
                        audit_log("medium_action_executed", action=action, description=desc)
                        await executer_une_action(d)
                    else:
                        await executer_une_action(d)
                return True

        if len(reponse) > 2:
            # Sauvegarde de la réponse naturelle
            stocker_souvenir(f"PHOEBUS a dit : {reponse}", source="conversation", importance=1)
            await parler(reponse)
            return True

    except Exception as e:
        print(f"Erreur traitement IA : {e}")
        await parler("Il y a eu un petit raté dans mon interprétation, Monsieur.")

    return False
