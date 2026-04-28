"""Observabilité — mesure de latence par phase + dashboard HTTP léger.

Objectif : savoir où Jarvis passe son temps. Chaque phase importante
(STT, LLM, TTS, action, synthèse de phrase, etc.) peut être mesurée via
un décorateur ou un context manager, et les temps sont conservés dans un
buffer circulaire en mémoire.

Un endpoint HTTP `/metrics` sur le serveur mobile existant (port 8080)
renvoie un JSON ou une page HTML minimaliste avec les derniers p50/p95
par phase. Zéro dépendance externe.

Usage :

    from PHOEBUS.observability import timed, measure

    @timed("ia.gemini")
    async def demander_ia(...): ...

    async def parler(...):
        async with measure("tts.synth"):
            await synthesize(...)
"""
import asyncio
import json
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from functools import wraps
from typing import Callable, Deque, Dict

from PHOEBUS.config import BASE_DIR


# ── Buffer ─────────────────────────────────────────────────────────────────

MAX_SAMPLES_PER_PHASE = 500
_samples: Dict[str, Deque[float]] = {}
REQUEST_METRICS_FILE = BASE_DIR / "logs" / "request_metrics.jsonl"
_request_samples: Deque[dict] = deque(maxlen=200)


def _record(phase: str, duration_ms: float) -> None:
    buf = _samples.get(phase)
    if buf is None:
        buf = deque(maxlen=MAX_SAMPLES_PER_PHASE)
        _samples[phase] = buf
    buf.append(duration_ms)


def reset() -> None:
    _samples.clear()
    _request_samples.clear()


# ── Instrumentation ───────────────────────────────────────────────────────

def timed(phase: str) -> Callable:
    """Décorateur à appliquer sur une coroutine ou fonction synchrone."""

    def deco(fn):
        if asyncio.iscoroutinefunction(fn):
            @wraps(fn)
            async def awrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    _record(phase, (time.perf_counter() - t0) * 1000.0)
            return awrapper

        @wraps(fn)
        def swrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                _record(phase, (time.perf_counter() - t0) * 1000.0)
        return swrapper

    return deco


@asynccontextmanager
async def measure(phase: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _record(phase, (time.perf_counter() - t0) * 1000.0)


@contextmanager
def measure_sync(phase: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _record(phase, (time.perf_counter() - t0) * 1000.0)


# ── Stats ─────────────────────────────────────────────────────────────────

def _percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def snapshot() -> dict:
    """Renvoie les stats courantes : {phase: {count, p50, p95, p99, last}}."""
    result = {}
    for phase, buf in _samples.items():
        if not buf:
            continue
        data = sorted(buf)
        result[phase] = {
            "count": len(data),
            "p50_ms": round(_percentile(data, 0.50), 1),
            "p95_ms": round(_percentile(data, 0.95), 1),
            "p99_ms": round(_percentile(data, 0.99), 1),
            "max_ms": round(data[-1], 1),
            "last_ms": round(buf[-1], 1),
        }
    return result


def record_request(
    *,
    source: str,
    duration_ms: float,
    ok: bool = True,
    route: str = "command",
    text_len: int = 0,
) -> None:
    item = {
        "ts": time.time(),
        "source": source,
        "route": route,
        "duration_ms": round(float(duration_ms), 1),
        "ok": bool(ok),
        "text_len": int(text_len),
    }
    _request_samples.append(item)
    try:
        REQUEST_METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(REQUEST_METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[METRICS] requête non enregistrée : {exc}")


def request_snapshot(limit: int = 50) -> dict:
    items = list(_request_samples)[-limit:]
    if not items and REQUEST_METRICS_FILE.exists():
        lines = REQUEST_METRICS_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
        for line in lines:
            try:
                items.append(json.loads(line))
            except Exception:
                continue
    durations = sorted(float(item.get("duration_ms", 0) or 0) for item in items)
    return {
        "count": len(items),
        "p50_ms": round(_percentile(durations, 0.50), 1) if durations else 0.0,
        "p95_ms": round(_percentile(durations, 0.95), 1) if durations else 0.0,
        "last": items[-1] if items else None,
        "recent": items[-10:],
    }


def render_html() -> str:
    """Petite page HTML pour consultation navigateur."""
    snap = snapshot()
    rows = "".join(
        f"<tr><td>{phase}</td>"
        f"<td class=n>{s['count']}</td>"
        f"<td class=n>{s['p50_ms']}</td>"
        f"<td class=n>{s['p95_ms']}</td>"
        f"<td class=n>{s['p99_ms']}</td>"
        f"<td class=n>{s['last_ms']}</td>"
        f"</tr>"
        for phase, s in sorted(snap.items())
    ) or '<tr><td colspan=6 class=n>(aucune donnée encore)</td></tr>'
    return f"""<!doctype html><meta charset=utf-8>
<title>JARVIS — métriques</title>
<style>
body{{font:14px/1.4 -apple-system,Segoe UI,sans-serif;background:#0a0b10;color:#e6ecf5;padding:28px;margin:0}}
h1{{font-weight:300;letter-spacing:3px;margin:0 0 18px;font-size:16px;color:#4ca8e8}}
table{{border-collapse:collapse;min-width:600px;background:#111217;border-radius:8px;overflow:hidden}}
th,td{{padding:8px 14px;border-bottom:1px solid #1c1f29;text-align:left}}
th{{background:#1a1d27;color:#8fb3d4;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:1.5px}}
.n{{text-align:right;font-variant-numeric:tabular-nums}}
tr:last-child td{{border:none}}
.meta{{color:#6e7988;font-size:11px;margin-top:18px;letter-spacing:1px}}
</style>
<h1>JARVIS METRICS</h1>
<table>
<tr><th>phase</th><th class=n>n</th><th class=n>p50</th><th class=n>p95</th><th class=n>p99</th><th class=n>last</th></tr>
{rows}
</table>
<p class=meta>auto-refresh 5s — temps en millisecondes</p>
<script>setTimeout(()=>location.reload(),5000);</script>
"""


def render_json() -> str:
    return json.dumps(
        {"phases": snapshot(), "requests": request_snapshot(), "ts": time.time()},
        ensure_ascii=False,
    )
