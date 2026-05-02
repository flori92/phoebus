#!/usr/bin/env sh
cd "$(dirname "$0")"

existing_pids="$(pgrep -f '[m]ain2.py' 2>/dev/null || true)"
if [ -n "$existing_pids" ]; then
  echo "[WATCHDOG] Instance précédente trouvée (PIDs: $(echo "$existing_pids" | tr '\n' ' ')). Arrêt forcé en cours..."
  kill -9 $existing_pids 2>/dev/null || true
  sleep 1
fi

LOCK_DIR="${TMPDIR:-/tmp}/phoebus-watchdog.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  if [ -f "$LOCK_DIR/pid" ] && kill -0 "$(cat "$LOCK_DIR/pid" 2>/dev/null)" 2>/dev/null; then
    echo "[WATCHDOG] Un watchdog PHOEBUS est déjà actif (PID $(cat "$LOCK_DIR/pid"))."
    exit 0
  fi
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" || exit 1
fi
echo "$$" > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

# --- AUTO-CLEANUP ---
# Libère les ports bloqués par des processus orphelins, après vérification
# qu'aucun core PHOEBUS actif n'est déjà lancé.
stale_port_pids="$(lsof -ti :8765,8090,8080 2>/dev/null | sort -u | tr '\n' ' ')"
if [ -n "$stale_port_pids" ]; then
  echo "[WATCHDOG] Nettoyage de ports orphelins : $stale_port_pids"
  kill $stale_port_pids 2>/dev/null || true
  sleep 1
  kill -9 $stale_port_pids 2>/dev/null || true
fi
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
  .venv/bin/python main2.py --auto-restart
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
