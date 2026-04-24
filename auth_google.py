import os
import sys

# S'assurer qu'on utilise l'environnement virtuel
in_venv = (sys.prefix != sys.base_prefix) or hasattr(sys, 'real_prefix')
venv_py = os.path.join(os.getcwd(), ".venv", "bin", "python")

if not in_venv and os.path.exists(venv_py):
    if sys.executable != venv_py:
        print("[SYSTEM] Passage sur l'environnement virtuel (.venv)...")
        os.execv(venv_py, [venv_py] + sys.argv)

from PHOEBUS.google_services import get_calendar_service

print("======================================================")
print("  RECONNEXION GOOGLE CALENDAR (Génération du Token)")
print("======================================================")
print("Une fenêtre de votre navigateur va s'ouvrir.")
print("Veuillez sélectionner votre compte Google et autoriser PHOEBUS.")
print("Patientez...")

try:
    service = get_calendar_service(interactive=True)
    if service:
        print("\n[SUCCÈS] Authentification réussie ! Le fichier token.pickle a été généré.")
        print("Vous pouvez maintenant relancer PHOEBUS (python3 main2.py).")
    else:
        print("\n[ÉCHEC] Impossible de créer le service Google. Vérifiez vos identifiants.")
except Exception as e:
    print(f"\n[ERREUR] Une erreur est survenue lors de l'authentification : {e}")
