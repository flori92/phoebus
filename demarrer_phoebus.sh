#!/usr/bin/env sh
cd "$(dirname "$0")"

# --- AUTO-CLEANUP ---
# Libère les ports bloqués par des instances précédentes (zombies)
lsof -ti :8765,8090,8080 | xargs kill -9 2>/dev/null || true
# --------------------

export PYTHONUTF8=1
export PYTHONIOENCODING=UTF-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

if [ ! -x ".venv/bin/python" ]; then
  python3 scripts/bootstrap.py
fi

echo "============================================================"
echo "      PHOEBUS WATCHDOG - SUPERVISION DU SYSTÈME ACTIF       "
echo "============================================================"

# Boucle de redémarrage automatique (watchdog)
while true; do
  echo "[WATCHDOG] Lancement de PHOEBUS..."
  # On passe --auto-restart pour éviter d'ouvrir 50 onglets dans le navigateur
  .venv/bin/python main2.py --auto-restart || true
  exit_code=$?
  
  if [ $exit_code -eq 0 ]; then
    echo "[WATCHDOG] PHOEBUS s'est arrêté proprement (Code 0). Fin du Watchdog."
    break
  elif [ $exit_code -eq 42 ]; then
    echo "[WATCHDOG] Commande de redémarrage (Code 42). Relance immédiate..."
    sleep 1
  else
    echo "[WATCHDOG] Crash inattendu (Code $exit_code). Redémarrage automatique dans 3 secondes..."
    sleep 3
  fi
done
