"""Cast media sur AirPlay (Apple TV / HomePod) et Chromecast.

PHOEBUS détecte les receivers AirPlay et Chromecast sur le LAN (via
mDNS, déjà fait par PHOEBUS.network) et peut envoyer une URL média ou
un YouTube vers le device choisi.

Dépendances optionnelles :
    pip install pychromecast    pour Chromecast / Google Cast
    pip install pyatv           pour AirPlay (Apple TV récents)

Sans ces libs, on signale gracieusement leur absence.

Actions :
- cast_list             : liste des receivers détectés
- cast_play             : envoie une URL à un receiver
- cast_youtube          : ouvre une vidéo YouTube sur le receiver
- cast_stop             : stop le playback
"""
import asyncio
from typing import List, Optional


# ── Détection receivers via mDNS (réutilise PHOEBUS.network) ───────────

async def list_receivers() -> List[dict]:
    """Renvoie les Apple TVs et Chromecasts vus sur le LAN."""
    from PHOEBUS.network import discover
    devices = await discover()
    receivers = []
    for d in devices:
        for s in d.get("services", []):
            stype = s.get("type", "")
            if "_airplay" in stype or "_googlecast" in stype or "_raop" in stype:
                receivers.append(
                    {
                        "ip": d.get("ip"),
                        "name": s.get("name", "").split("._")[0] or d.get("hostname", ""),
                        "kind": "chromecast" if "_googlecast" in stype else "airplay",
                        "port": s.get("port"),
                    }
                )
    # Déduplication par (ip, kind)
    seen = set()
    uniq = []
    for r in receivers:
        k = (r["ip"], r["kind"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


# ── Chromecast ───────────────────────────────────────────────────────────

def _cast_chromecast_sync(name_or_ip: str, url: str, mime: str = "video/mp4") -> str:
    try:
        import pychromecast  # type: ignore
    except Exception:
        return "pychromecast non installé. `pip install pychromecast`."
    try:
        chromecasts, browser = pychromecast.get_chromecasts(timeout=4)
        cast = None
        for cc in chromecasts:
            ident = cc.cast_info
            if (
                getattr(ident, "friendly_name", "") == name_or_ip
                or getattr(ident, "host", "") == name_or_ip
            ):
                cast = cc
                break
        if cast is None and chromecasts:
            cast = chromecasts[0]
        if cast is None:
            try:
                browser.stop_discovery()
            except Exception:
                pass
            return "Aucun Chromecast trouvé."
        cast.wait()
        mc = cast.media_controller
        mc.play_media(url, mime)
        mc.block_until_active()
        try:
            browser.stop_discovery()
        except Exception:
            pass
        return f"Lecture lancée sur {getattr(cast.cast_info, 'friendly_name', 'Chromecast')}."
    except Exception as e:
        return f"Chromecast KO : {e}"


# ── AirPlay (pyatv) ──────────────────────────────────────────────────────

async def _cast_airplay(name_or_ip: str, url: str) -> str:
    try:
        import pyatv  # type: ignore
        from pyatv import scan, connect
        from pyatv.const import Protocol
    except Exception:
        return "pyatv non installé. `pip install pyatv`."

    loop = asyncio.get_event_loop()
    try:
        atvs = await scan(loop, timeout=4)
        target = None
        for a in atvs:
            if (a.name or "").lower() == name_or_ip.lower() or str(a.address) == name_or_ip:
                target = a
                break
        if target is None and atvs:
            target = atvs[0]
        if target is None:
            return "Aucune Apple TV trouvée."

        atv = await connect(target, loop, protocol=Protocol.AirPlay)
        try:
            await atv.stream.play_url(url)
        finally:
            atv.close()
        return f"Diffusion AirPlay lancée sur {target.name}."
    except Exception as e:
        return f"AirPlay KO : {e}"


# ── API publique ─────────────────────────────────────────────────────────

async def cast_play(target: str, url: str, kind: Optional[str] = None) -> str:
    """Envoie `url` vers `target` (nom ou IP). `kind` optionnel : 'airplay' ou 'chromecast'.

    Si kind est None, on déduit du LAN scan : si le target est une Apple TV
    on prend AirPlay, sinon Chromecast.
    """
    if not url:
        return "URL manquante."
    if not target:
        return "Receiver cible manquant."

    receivers = await list_receivers()
    chosen = None
    for r in receivers:
        if r["name"].lower() == target.lower() or r["ip"] == target:
            chosen = r
            break

    use_kind = kind or (chosen["kind"] if chosen else "chromecast")

    if use_kind == "airplay":
        return await _cast_airplay(target, url)
    return await asyncio.to_thread(_cast_chromecast_sync, target, url)


async def cast_youtube(target: str, query_or_url: str) -> str:
    """Lance une vidéo YouTube sur le receiver. Accepte URL ou query."""
    if "youtube.com/watch" in query_or_url or "youtu.be/" in query_or_url:
        url = query_or_url
    else:
        # Recherche simple : on construit l'URL "résultat de recherche".
        # YouTube redirige souvent vers la 1re vidéo dans Chromecast.
        import urllib.parse
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(
            query_or_url
        )
    return await cast_play(target, url, kind="chromecast")


async def cast_stop(target: str) -> str:
    """Stop le playback en cours."""
    try:
        import pychromecast  # type: ignore
        chromecasts, browser = pychromecast.get_chromecasts(timeout=3)
        for cc in chromecasts:
            if (
                getattr(cc.cast_info, "friendly_name", "") == target
                or getattr(cc.cast_info, "host", "") == target
            ):
                cc.wait()
                cc.media_controller.stop()
                try:
                    browser.stop_discovery()
                except Exception:
                    pass
                return "Playback arrêté."
        return "Receiver non trouvé."
    except Exception as e:
        return f"Stop KO : {e}"
