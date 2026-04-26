"""Exécuteur Python contraint pour PHOEBUS.

Permet à PHOEBUS de **calculer**, **scripter** et **explorer** à la demande
sans dépendre d'un appel LLM pour des opérations déterministes :
  - "calcule la 47e décimale de pi"
  - "convertis 3500 USD en EUR au taux du jour"
  - "combien d'octets dans un Go ?"
  - "donne-moi un mot de passe aléatoire de 16 caractères"

Sécurité (ce n'est PAS un sandbox cryptographique, mais une protection
raisonnable contre l'erreur stupide) :
  - subprocess séparé avec timeout 5 s.
  - import-list whitelist : math, statistics, random, datetime, json,
    re, hashlib, base64, secrets, decimal, fractions, itertools, string,
    urllib.parse, ipaddress, uuid, textwrap, collections.
  - pas d'accès fichier hors /tmp.
  - le code est inspecté avant exécution pour rejeter :
      open(...) hors /tmp, exec(), eval(), subprocess, os.system,
      __import__, __builtins__, network sockets, file:// urls.

Action exposée : `python_run` avec champ `code`. Capture stdout + stderr.
"""
import os
import re
import subprocess
import sys
import tempfile
import textwrap

from PHOEBUS.observability import measure


WHITELISTED_IMPORTS = {
    "math", "statistics", "random", "datetime", "json", "re", "hashlib",
    "base64", "secrets", "decimal", "fractions", "itertools", "string",
    "urllib.parse", "ipaddress", "uuid", "textwrap", "collections",
    "calendar", "time", "functools", "operator", "bisect", "heapq",
    "zoneinfo",
}

FORBIDDEN_PATTERNS = [
    re.compile(r"\bos\.system\b"),
    re.compile(r"\bsubprocess\b"),
    re.compile(r"\b__import__\b"),
    re.compile(r"\b__builtins__\b"),
    re.compile(r"\bcompile\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bsocket\b"),
    re.compile(r"\bopen\s*\(\s*[\"'](?!/tmp/)[^\"']*[\"']"),  # open hors /tmp
    re.compile(r"file://"),
    re.compile(r"\brequests\b"),
    re.compile(r"\bhttp\.client\b"),
    re.compile(r"\bsmtplib\b"),
    re.compile(r"\bpickle\b"),
    re.compile(r"\bshutil\b"),
    re.compile(r"\bpathlib\b"),
]


def _audit(code: str) -> str | None:
    """Renvoie un message d'erreur si le code viole les règles, sinon None."""
    if not code or not code.strip():
        return "Code vide."
    if len(code) > 8000:
        return "Code trop long (>8000 caractères)."

    # Imports : seuls les modules de WHITELISTED_IMPORTS sont autorisés.
    for line in code.splitlines():
        s = line.strip()
        if s.startswith("import "):
            mods = re.split(r",", s[len("import ") :])
            for m in mods:
                m = m.strip().split(" as ")[0].strip()
                base = m.split(".")[0]
                if base not in WHITELISTED_IMPORTS and m not in WHITELISTED_IMPORTS:
                    return f"Module non autorisé : {m}"
        elif s.startswith("from "):
            mod = s[len("from ") :].split(" import ")[0].strip()
            base = mod.split(".")[0]
            if base not in WHITELISTED_IMPORTS and mod not in WHITELISTED_IMPORTS:
                return f"Module non autorisé : {mod}"

    for pat in FORBIDDEN_PATTERNS:
        if pat.search(code):
            return f"Motif interdit détecté : {pat.pattern}"
    return None


async def run_python(code: str, timeout_s: float = 5.0) -> dict:
    """Exécute le code Python dans un subprocess. Renvoie un dict :
    { ok: bool, stdout: str, stderr: str, exit_code: int, reason?: str }
    """
    err = _audit(code)
    if err is not None:
        return {"ok": False, "stdout": "", "stderr": "", "exit_code": -1, "reason": err}

    # On enveloppe le code pour qu'il s'exécute dans un module isolé.
    # Auto-print du dernier résultat si c'est une expression simple.
    wrapper = textwrap.dedent(
        f"""
        import sys
        sys.dont_write_bytecode = True
        try:
{textwrap.indent(code, "            ")}
        except Exception as _phoebus_err:
            import traceback
            traceback.print_exc()
            sys.exit(1)
        """
    )

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="phoebus_run_", delete=False, dir="/tmp"
    )
    try:
        tmp.write(wrapper)
        tmp.flush()
        tmp.close()

        async with measure("code.python_run"):
            import asyncio
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-I", "-S", tmp.name,  # -I isolé, -S no site
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                out, err_out = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return {
                    "ok": False, "stdout": "", "stderr": "",
                    "exit_code": -2, "reason": f"Timeout après {timeout_s}s",
                }

        return {
            "ok": proc.returncode == 0,
            "stdout": (out or b"").decode("utf-8", errors="replace")[:4000],
            "stderr": (err_out or b"").decode("utf-8", errors="replace")[:1000],
            "exit_code": proc.returncode,
        }
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def format_result_for_speech(result: dict) -> str:
    """Convertit le dict de résultat en phrase pour parler()."""
    if not result.get("ok"):
        if result.get("reason"):
            return f"Code refusé : {result['reason']}"
        return f"Le code a planté : {result.get('stderr', '')[:200]}"
    out = (result.get("stdout") or "").strip()
    if not out:
        return "Le code s'est exécuté sans rien afficher."
    # Tronque pour la voix.
    if len(out) > 600:
        return out[:600] + "... (j'arrête là, c'est trop long pour la voix)"
    return out
