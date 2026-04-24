# jarvis/voice.py
"""Synthèse vocale (TTS), reconnaissance (STT) et logique de fallback local."""
import re
import math
import time
import json
import base64
import asyncio
import threading
import webbrowser

from jarvis.config import edge_tts, pygame, pyaudio, sr, CLAP_THRESHOLD, pyautogui
import jarvis.state as state
from jarvis.home import resolve_ha_entity, PIECES_LUMIERES, ha_get_etat, ha_lumiere
from jarvis.tts_backends import synthesize_to_file, TtsUnavailable, EDGE_VOICE
from jarvis.text_shaping import naturaliser
from jarvis.response_cache import lookup as cache_lookup, register as cache_register
from jarvis.sentence_splitter import split as split_sentences

# ── Résolution locale (Math, Fr, Conversions, Trad) ──────────────────────

def reponse_locale(texte):
    t = texte.lower().strip()
    if any(m in t for m in ["qui es-tu", "ton nom", "quelle es ton identité"]):
        return "Je suis JARVIS. Mes serveurs sont actuellement en maintenance, mais je reste opérationnel localement."
    if any(m in t for m in ["ton créateur", "t'as créé", "qui est floriace"]):
        return "Floriace est mon créateur."
    if any(m in t for m in ["ça va", "tu vas bien"]):
        return "Je fonctionne en mode de réserve, Floriace."
    if any(m in t for m in ["heure", "quelle heure"]):
        return f"Il est précisément {time.strftime('%H:%M')} Monsieur."
    if any(m in t for m in ["date", "quel jour"]):
        return f"Nous sommes le {time.strftime('%A %d %B %Y')}."
    if any(m in t for m in ["bonjour", "salut"]):
        return "Bonjour Floriace."
    return None

def resoudre_math_localement(texte):
    t = texte.lower().replace("?", "").strip()
    for prefixe in ["combien font", "calcule", "résous", "quel est le résultat de"]:
        if t.startswith(prefixe): t = t[len(prefixe):].strip()
    t = t.replace("fois", "*").replace("multiplier par", "*").replace("x", "*")
    t = t.replace("divisé par", "/").replace("sur", "/")
    t = t.replace("plus", "+").replace("moins", "-")
    t = t.replace("puissance", "**").replace("au carré", "**2")
    if "racine" in t:
        match = re.search(r'racine\s+(?:carrée\s+de\s+)?(\d+)', t)
        if match: t = f"sqrt({match.group(1)})"
        else: t = t.replace("racine carrée de", "sqrt").replace("racine de", "sqrt")
    expr = re.sub(r'[^0-9+\-*/.**() ,sqrt]', '', t).strip()
    if not expr or not any(c.isdigit() for c in expr): return None
    try:
        safe_dict = {"sqrt": math.sqrt, "pow": math.pow, "pi": math.pi, "e": math.e}
        res = eval(expr, {"__builtins__": None}, safe_dict)
        if isinstance(res, float) and res.is_integer(): res = int(res)
        elif isinstance(res, float): res = round(res, 3)
        return f"Le résultat de {expr} est {res}, Monsieur."
    except Exception:
        return None

def resoudre_francais_localement(texte):
    t = texte.lower().strip()
    dic = {
        "ia": "Intelligence Artificielle.",
        "jarvis": "Just A Rather Very Intelligent System.",
    }
    for p in ["définition de", "définis le mot", "c'est quoi"]:
        if p in t:
            mot = t.split(p)[-1].replace("?", "").strip()
            if mot in dic: return f"La définition est : {dic[mot]}."
    if "conjugue" in t and "être" in t:
        return "Je suis, tu es, il est, nous sommes, vous êtes, ils sont."
    return None

def resoudre_conversion_localement(texte):
    t = texte.lower().replace("?", "").strip()
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:km|kilomètres)', t)
    if match: return f"{match.group(1)} kilomètres font environ {round(float(match.group(1).replace(',', '.')) * 0.621371, 2)} miles."
    return None

def resoudre_traduction_localement(texte):
    t = texte.lower().strip()
    dic = {"bonjour": {"en": "hello"}, "merci": {"en": "thank you"}}
    if "en anglais" in t:
        for k, v in dic.items():
            if k in t: return f"En anglais, '{k}' se dit '{v['en']}'."
    return None


# ── TTS (Edge-TTS + Pygame) ────────────────────────────────────────────────

def init_mixer():
    if not pygame: return False
    if not pygame.mixer.get_init(): pygame.mixer.init()
    return True

async def _prepare_tts(sentence):
    """Prépare le fichier audio d'une phrase. Renvoie (path, is_cache).

    Consulte le cache avant tout. Si miss, synthétise puis archive. Si
    aucun back-end TTS n'est disponible, émet un fallback WS et renvoie
    (None, False)."""
    cached = cache_lookup(sentence, EDGE_VOICE, "auto")
    if cached is not None:
        return (str(cached), True)
    tmp = f"jarvis_tts_{int(time.time()*1_000_000)}.mp3"
    try:
        await synthesize_to_file(sentence, tmp)
        cache_register(sentence, EDGE_VOICE, "auto", tmp)
        return (tmp, False)
    except TtsUnavailable:
        recipients = state.get_authenticated_clients()
        if recipients:
            msg = json.dumps({"action": "jarvis_response", "text": sentence})
            await asyncio.gather(*[ws.send(msg) for ws in recipients], return_exceptions=True)
        return (None, False)


async def _play_file(path, is_cache, texte_tts):
    """Joue un fichier audio via pygame (PC) ou via WebSocket (mobile web)."""
    try:
        if state._skip_pc_audio:
            recipients = state.get_authenticated_clients()
            if recipients:
                try:
                    with open(path, "rb") as f:
                        audio_b64 = base64.b64encode(f.read()).decode('utf-8')
                    msg = json.dumps({"action": "jarvis_audio", "text": texte_tts, "audio_b64": audio_b64})
                    await asyncio.gather(*[ws.send(msg) for ws in recipients], return_exceptions=True)
                except Exception as e:
                    print(f"[MOBILE] Erreur envoi audio : {e}")
        else:
            if not init_mixer():
                recipients = state.get_authenticated_clients()
                if recipients:
                    msg = json.dumps({"action": "jarvis_response", "text": texte_tts})
                    await asyncio.gather(*[ws.send(msg) for ws in recipients], return_exceptions=True)
                return

            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if state.STOP_PARLER:
                    pygame.mixer.music.stop()
                    break
                t_audio = time.time() * 20
                base_vol = 0.4 + 0.3 * math.sin(t_audio) + 0.2 * math.sin(t_audio * 0.5)
                state.speak_volume = max(0.1, min(1.0, base_vol + 0.1))
                await state.send_web_volume(state.speak_volume)
                await asyncio.sleep(0.05)
    except Exception as e:
        print(f"Erreur TTS : {e}")
    finally:
        try:
            if pygame and pygame.mixer.get_init():
                pygame.mixer.music.unload()
        except: pass
        if not is_cache:
            try:
                import os
                if os.path.exists(path): os.remove(path)
            except: pass


async def parler(texte):
    """Synthétise et joue un texte avec pipeline phrase-par-phrase.

    La phrase N+1 est synthétisée EN PARALLÈLE de la lecture de la phrase N,
    ce qui divise la latence totale d'un gros paragraphe par ~2.
    La phrase 1 bénéficie en plus du cache pré-chauffé au démarrage.
    """
    texte_tts = naturaliser(texte)

    if state.historique and len(state.historique) > 0:
        if state.historique[-1].parts[0].text != texte:
            state.ajouter_historique("model", f"[Info retournée par l'action et énoncée à voix haute]: {texte}")

    state.extend_conversation()

    sentences = split_sentences(texte_tts)
    if not sentences:
        return

    state.is_speaking = True
    await state.send_web_state("speaking")
    state.speak_volume = 0.0

    try:
        # ── Pipeline : pendant qu'on joue N, on synthétise N+1. ───────────
        prep_task = asyncio.create_task(_prepare_tts(sentences[0]))
        for i, s in enumerate(sentences):
            try:
                result = await prep_task
            except Exception as e:
                print(f"[TTS] prep '{s[:40]}...' : {e}")
                result = (None, False)

            # Lance tout de suite la préparation de la phrase suivante.
            next_task = None
            if i + 1 < len(sentences):
                next_task = asyncio.create_task(_prepare_tts(sentences[i + 1]))

            if state.STOP_PARLER:
                if next_task:
                    next_task.cancel()
                break

            path, is_cache = result
            if path is not None:
                await _play_file(path, is_cache, s)

            if state.STOP_PARLER:
                if next_task:
                    next_task.cancel()
                break

            prep_task = next_task
    except Exception as e:
        print(f"Erreur TTS : {e}")
    finally:
        state.speak_volume = 0.0
        state.is_speaking = False
        state.STOP_PARLER = False
        await asyncio.sleep(0.05)
        await state.send_web_state("idle")


# ── Claps Monitoring ───────────────────────────────────────────────────────

def monitor_claps():
    if not pyaudio:
        print("[CLAP] PyAudio indisponible.")
        return
    try:
        import audioop
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
        last_clap_time = 0
        barge_in_streak = 0

        while True:
            try:
                data = stream.read(1024, exception_on_overflow=False)
                rms  = audioop.rms(data, 2)

                # ── Barge-in : si Jarvis parle et on détecte de la voix forte,
                # on coupe proprement pour écouter la suite.
                if state.is_speaking:
                    if rms > state.BARGE_IN_THRESHOLD:
                        barge_in_streak += 1
                        if barge_in_streak >= state.BARGE_IN_CONSECUTIVE_CHUNKS:
                            print("[BARGE-IN] Interruption vocale détectée, Jarvis se tait.")
                            state.STOP_PARLER = True
                            barge_in_streak = 0
                    else:
                        barge_in_streak = 0
                    # On ne fait pas de clap-detection pendant que Jarvis parle.
                    last_clap_time = 0
                    continue
                else:
                    barge_in_streak = 0

                if not state.MODE_IRON_MAN or state.is_thinking:
                    last_clap_time = 0
                    continue

                if rms > CLAP_THRESHOLD:
                    current_time = time.time()
                    diff = current_time - last_clap_time
                    if 0.1 < diff < 0.8:
                        print(f"\n[CLAP] !!! DOUBLE CLAP DETECTE !!!")
                        entity_id = resolve_ha_entity("light", "salon", PIECES_LUMIERES, default_prefix="light")
                        etat_actuel = ha_get_etat(entity_id)
                        
                        if etat_actuel != "on":
                            ha_lumiere(entity_id, "on")
                            if not state.VIDEO_LANCEE:
                                webbrowser.open("https://www.youtube.com/watch?v=KU5V5WZVcVE")
                                state.VIDEO_LANCEE = True
                                def seq():
                                    time.sleep(5)
                                    if pyautogui: pyautogui.press('f')
                                threading.Thread(target=seq, daemon=True).start()
                            else:
                                if pyautogui: pyautogui.press('k')
                        else:
                            ha_lumiere(entity_id, "off")
                            if state.VIDEO_LANCEE and pyautogui:
                                pyautogui.press('k')
                        time.sleep(3.0)
                        last_clap_time = 0
                    else:
                        last_clap_time = current_time
            except Exception:
                time.sleep(0.5)
                continue
    except Exception as e:
        print(f"[CLAP] Erreur fatale : {e}")
