import speech_recognition as sr
print("Testing microphone...")
r = sr.Recognizer()
try:
    with sr.Microphone() as source:
        print("Ajustement au bruit ambiant...")
        r.adjust_for_ambient_noise(source, duration=2)
        print(f"Energy threshold defini à : {r.energy_threshold}")
        print("Parlez maintenant ! (5 secondes max)")
        audio = r.listen(source, timeout=5, phrase_time_limit=5)
        print("Audio capturé. Reconnaissance en cours...")
        texte = r.recognize_google(audio, language="fr-FR")
        print(f"Resultat: {texte}")
except sr.WaitTimeoutError:
    print("Timeout: Aucun son n'a depassé le seuil d'énergie.")
except Exception as e:
    print(f"Erreur: {e}")
