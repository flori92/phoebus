# jarvis/utils.py
"""Utilitaires système partagés par les modules JARVIS."""
import os
import re
import shutil
import socket
import subprocess
import unicodedata
import webbrowser
from pathlib import Path

from jarvis.config import IS_WINDOWS, IS_MACOS, SYSTEM_NAME


def get_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def find_available_port(start_port, host="0.0.0.0", max_tries=20):
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Aucun port libre trouve a partir de {start_port}.")


def normalize_text(value):
    value = str(value or "").strip().lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", value)


def special_folder(name):
    home = Path.home()
    mapping = {
        "bureau": "Desktop", "desktop": "Desktop",
        "documents": "Documents",
        "telechargements": "Downloads", "downloads": "Downloads",
        "images": "Pictures", "photos": "Pictures",
        "videos": "Videos", "musique": "Music",
    }
    folder = mapping.get(name.lower())
    if not folder:
        return Path(name).expanduser()
    candidate = home / folder
    return candidate if candidate.exists() else home


def open_path(path):
    path = str(Path(path).expanduser())
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    elif IS_MACOS:
        subprocess.Popen(["open", path])
    else:
        opener = shutil.which("xdg-open") or shutil.which("gio")
        if opener:
            subprocess.Popen([opener, path])
        else:
            raise RuntimeError("Aucun outil d'ouverture de dossier trouve (xdg-open/gio).")


def open_uri(uri):
    if IS_WINDOWS:
        os.startfile(uri)  # type: ignore[attr-defined]
    elif IS_MACOS:
        subprocess.Popen(["open", uri])
    else:
        opener = shutil.which("xdg-open") or shutil.which("gio")
        if opener:
            subprocess.Popen([opener, uri])
        else:
            webbrowser.open(uri)


def launch_app(app_name):
    app_name = app_name.lower()
    candidates = {
        "chrome": {
            "Windows": [["chrome.exe"]],
            "Darwin":  [["open", "-a", "Google Chrome"], ["open", "-a", "Chrome"]],
            "Linux":   [["google-chrome"], ["chromium"], ["chromium-browser"]],
        },
        "notepad": {
            "Windows": [["notepad.exe"]],
            "Darwin":  [["open", "-a", "TextEdit"]],
            "Linux":   [["gedit"], ["kate"], ["xed"], ["nano"]],
        },
        "explorer": {
            "Windows": [["explorer.exe"]],
            "Darwin":  [["open", str(Path.home())]],
            "Linux":   [["xdg-open", str(Path.home())]],
        },
    }
    for cmd in candidates.get(app_name, {}).get(SYSTEM_NAME, []):
        executable = cmd[0]
        if executable in {"open", "xdg-open"} or shutil.which(executable):
            subprocess.Popen(cmd)
            return True
    return False


def desktop_file(name):
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path.home()
    return desktop / name


def shutdown_system(delay_seconds=5):
    if IS_WINDOWS:
        subprocess.Popen(["shutdown", "/s", "/t", str(delay_seconds)])
    elif IS_MACOS:
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
    else:
        subprocess.Popen(["shutdown", "-h", f"+{max(1, delay_seconds // 60)}"])


def npm_command():
    return shutil.which("npm.cmd" if IS_WINDOWS else "npm") or shutil.which("npm")


def terminate_process_tree(process):
    if not process:
        return
    try:
        if IS_WINDOWS:
            taskkill = shutil.which("taskkill")
            if taskkill:
                subprocess.run([taskkill, "/F", "/T", "/PID", str(process.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        else:
            process.terminate()
            try:
                process.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                process.kill()
                return
        process.terminate()
    except Exception as e:
        print(f"[JARVIS] Impossible d'arreter le processus enfant : {e}")
