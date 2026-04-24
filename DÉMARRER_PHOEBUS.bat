@echo off
setlocal
TITLE PHOEBUS
COLOR 0B
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [PHOEBUS] Installation de l'environnement...
  py scripts\bootstrap.py
  if errorlevel 1 goto error
)

echo [PHOEBUS] Demarrage...
".venv\Scripts\python.exe" "main2.py"
goto end

:error
echo [PHOEBUS] Installation impossible. Verifiez Python 3.10+ et Node.js LTS.

:end
pause
