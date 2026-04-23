@echo off
setlocal
TITLE J.A.R.V.I.S
COLOR 0B
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [JARVIS] Installation de l'environnement...
  py scripts\bootstrap.py
  if errorlevel 1 goto error
)

echo [JARVIS] Demarrage...
".venv\Scripts\python.exe" "main2.py"
goto end

:error
echo [JARVIS] Installation impossible. Verifiez Python 3.10+ et Node.js LTS.

:end
pause
