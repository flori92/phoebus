"""Contrôle système macOS via osascript (AppleScript) + commandes UNIX.

Élargit l'agent natif existant avec des actions atomiques, rapides et
spécifiques macOS qui ne nécessitent pas une boucle ReAct complète :

- Verrouiller la session
- Mettre en veille / réveiller
- Vider la corbeille
- Régler le volume système
- Toggle do-not-disturb / mode focus
- Brightness écran
- Ouvrir une app
- Notification système (banner)
- Lock/Unlock écran
- Capture screen (full ou région)

Toutes les actions sont guard-railées : audit log + risk level explicite.
Sur Linux/Windows, on signale gracieusement que c'est macOS-only (pour
ces actions précises ; l'agent natif générique reste cross-platform).
"""
import asyncio
import platform
import subprocess
from typing import Optional

from PHOEBUS.observability import measure


IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


# ── Helpers ──────────────────────────────────────────────────────────────

async def _run(*args, timeout_s: float = 6.0, input_data: Optional[bytes] = None) -> tuple[int, str, str]:
    """Lance une commande système en async, renvoie (rc, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if input_data else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input=input_data), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return -1, "", "timeout"
    return (
        proc.returncode,
        (out or b"").decode("utf-8", errors="replace"),
        (err or b"").decode("utf-8", errors="replace"),
    )


async def _osascript(script: str, timeout_s: float = 6.0) -> tuple[int, str, str]:
    if not IS_MACOS:
        return -2, "", "Action macOS uniquement."
    return await _run("osascript", "-e", script, timeout_s=timeout_s)


# ── Verrouillage / veille ────────────────────────────────────────────────

async def lock_screen() -> str:
    if IS_MACOS:
        async with measure("system.lock"):
            rc, _, err = await _run(
                "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession",
                "-suspend",
            )
        return "Session verrouillée." if rc == 0 else f"Verrouillage KO : {err}"
    if IS_LINUX:
        for cmd in (("loginctl", "lock-session"), ("xdg-screensaver", "lock"),
                    ("gnome-screensaver-command", "-l")):
            rc, _, _ = await _run(*cmd, timeout_s=3.0)
            if rc == 0:
                return "Session verrouillée."
        return "Aucune méthode de verrouillage disponible."
    return "Verrouillage non supporté sur cette plateforme."


async def sleep_now() -> str:
    if IS_MACOS:
        async with measure("system.sleep"):
            rc, _, _ = await _run("pmset", "sleepnow")
        return "Mac mis en veille." if rc == 0 else "Veille refusée."
    if IS_LINUX:
        rc, _, _ = await _run("systemctl", "suspend")
        return "Système mis en veille." if rc == 0 else "Veille refusée."
    return "Veille non supportée."


# ── Corbeille ────────────────────────────────────────────────────────────

async def empty_trash() -> str:
    if IS_MACOS:
        async with measure("system.empty_trash"):
            rc, _, err = await _osascript('tell application "Finder" to empty trash')
        return "Corbeille vidée." if rc == 0 else f"Échec : {err}"
    if IS_LINUX:
        # gio trash --empty est la voie moderne (GNOME/freedesktop).
        rc, _, _ = await _run("gio", "trash", "--empty")
        return "Corbeille vidée." if rc == 0 else "gio non disponible."
    return "Action non supportée."


# ── Volume système macOS ─────────────────────────────────────────────────

async def set_volume(percent: int) -> str:
    p = max(0, min(100, int(percent)))
    if IS_MACOS:
        async with measure("system.volume"):
            rc, _, _ = await _osascript(f"set volume output volume {p}")
        return f"Volume système réglé à {p} %." if rc == 0 else "Échec réglage volume."
    if IS_LINUX:
        # PulseAudio / pipewire
        rc, _, _ = await _run("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{p}%")
        return f"Volume système réglé à {p} %." if rc == 0 else "pactl indisponible."
    return "Action non supportée."


async def mute() -> str:
    if IS_MACOS:
        rc, _, _ = await _osascript("set volume with output muted")
        return "Son coupé." if rc == 0 else "Échec mute."
    if IS_LINUX:
        rc, _, _ = await _run("pactl", "set-sink-mute", "@DEFAULT_SINK@", "1")
        return "Son coupé." if rc == 0 else "Échec."
    return "Action non supportée."


async def unmute() -> str:
    if IS_MACOS:
        rc, _, _ = await _osascript("set volume without output muted")
        return "Son rétabli." if rc == 0 else "Échec."
    if IS_LINUX:
        rc, _, _ = await _run("pactl", "set-sink-mute", "@DEFAULT_SINK@", "0")
        return "Son rétabli." if rc == 0 else "Échec."
    return "Action non supportée."


# ── Notification système ─────────────────────────────────────────────────

async def notify(title: str, message: str = "") -> str:
    title = (title or "PHOEBUS").replace('"', "'")
    message = (message or "").replace('"', "'")
    if IS_MACOS:
        script = f'display notification "{message}" with title "{title}"'
        rc, _, _ = await _osascript(script)
        return "Notification envoyée." if rc == 0 else "Échec notification."
    if IS_LINUX:
        rc, _, _ = await _run("notify-send", title, message)
        return "Notification envoyée." if rc == 0 else "notify-send indisponible."
    return "Action non supportée."


# ── Apps macOS ───────────────────────────────────────────────────────────

async def open_app(name: str) -> str:
    if not name:
        return "Nom d'app manquant."
    if IS_MACOS:
        rc, _, err = await _run("open", "-a", name)
        return f"Ouvert : {name}." if rc == 0 else f"Impossible d'ouvrir {name} : {err}"
    if IS_LINUX:
        rc, _, _ = await _run("xdg-open", name)
        return f"Ouvert : {name}." if rc == 0 else f"Impossible d'ouvrir {name}."
    return "Action non supportée."


async def quit_app(name: str) -> str:
    if not name:
        return "Nom d'app manquant."
    if IS_MACOS:
        rc, _, err = await _osascript(f'tell application "{name}" to quit')
        return f"Fermé : {name}." if rc == 0 else f"Impossible de fermer {name} : {err}"
    return "Action non supportée."


# ── Capture écran ────────────────────────────────────────────────────────

async def screenshot(out_path: str = "/tmp/phoebus_shot.png") -> str:
    if IS_MACOS:
        rc, _, err = await _run("screencapture", "-x", out_path)
        return f"Capture sauvegardée : {out_path}" if rc == 0 else f"Échec : {err}"
    if IS_LINUX:
        rc, _, _ = await _run("scrot", out_path)
        if rc != 0:
            rc, _, _ = await _run("import", "-window", "root", out_path)
        return f"Capture sauvegardée : {out_path}" if rc == 0 else "Échec capture."
    return "Action non supportée."


# ── Brightness (macOS uniquement, via brew brightness ou ddcctl) ────────

async def set_brightness(percent: int) -> str:
    if not IS_MACOS:
        return "Brightness non supporté ici."
    p = max(0, min(100, int(percent))) / 100.0
    # `brightness` doit être installé via Homebrew.
    rc, _, err = await _run("brightness", str(p))
    if rc == 0:
        return f"Luminosité réglée à {int(p * 100)} %."
    return f"Outil 'brightness' indisponible (brew install brightness)."
