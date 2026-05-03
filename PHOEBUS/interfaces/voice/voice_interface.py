# phoebus/interfaces/voice/voice_interface.py
import os
import asyncio
from typing import Optional

class VoiceInterface:
    def __init__(self):
        # Initialisation différée pour ne pas ralentir le boot si non utilisé
        self.whisper_model = None
        self.tts_client = None
        self.porcupine = None
    
    async def listen(self, duration: int = 5) -> str:
        """Écoute et transcrit via Whisper ou STT existant"""
        print("🎤 J'écoute...")
        try:
            from PHOEBUS.voice import sr
            # Utilisation de SpeechRecognition existant comme fallback rapide
            import speech_recognition as sr_lib
            recognizer = sr_lib.Recognizer()
            with sr_lib.Microphone() as source:
                audio = recognizer.listen(source, timeout=duration, phrase_time_limit=duration)
                return recognizer.recognize_google(audio, language="fr-FR")
        except Exception as e:
            print(f"[VOICE] Erreur écoute : {e}")
            return ""
    
    async def speak(self, text: str):
        """Parle via ElevenLabs ou Edge-TTS existant"""
        try:
            from PHOEBUS.voice import parler
            await parler(text)
        except Exception as e:
            print(f"[VOICE] Erreur parole : {e}")
            print(f"TEXTE: {text}")
    
    def wait_for_wake_word(self):
        """Attend le mot de réveil"""
        # Placeholder - on utilisera OpenWakeWord ou Porcupine si configuré
        print("💤 En attente du mot de réveil...")
        # Pour l'instant on simule une activation immédiate ou via CLI
        return True
