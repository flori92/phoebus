"""Automatisation navigateur via Playwright.

Installation (optionnel) :
    pip install playwright
    playwright install chromium

Deux modes :

1. **Navigation simple** (`url` fourni) : Jarvis ouvre la page, attend le
   chargement, puis ferme. Utile pour "ouvre YouTube", "va sur mon Gmail".

2. **Script Python restreint** (`script` fourni) : on exécute un script
   fourni dans un sandbox mini-restreint avec accès à l'objet `page`,
   `context` et `browser`. À utiliser avec **extrême prudence** — marqué
   `risk=high`, confirmation vocale obligatoire.

Cette skill tourne en mode `headless=false` par défaut (tu vois ce qui se
passe). Basculable via env `PLAYWRIGHT_HEADLESS=1`.
"""
import asyncio
import os
from typing import Optional


PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "0").strip().lower() in (
    "1", "true", "yes", "on",
)
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "15000"))


async def run(script: str = "", url: str = "") -> str:
    """Exécute une tâche Playwright. Renvoie un résumé texte à annoncer."""
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        return (
            "Playwright n'est pas installé. Lance `pip install playwright` "
            "puis `playwright install chromium`."
        )

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(PLAYWRIGHT_TIMEOUT_MS)

            if url:
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    title = await page.title()
                    msg = f"Page ouverte : {title[:80]}." if title else "Page ouverte."
                except Exception as e:
                    msg = f"Échec navigation : {e}"
                if not script:
                    # Laisse ouvert quelques secondes pour que Floriace voie la page
                    # puis referme proprement. En headless, on referme de suite.
                    if not PLAYWRIGHT_HEADLESS:
                        await asyncio.sleep(8)
                    await browser.close()
                    return msg

            if script:
                # Exécution restreinte : on ne donne accès qu'à page/context/browser.
                # Note : un script Python reste puissant ; confirmation vocale requise
                # en amont (action est déjà classée high-risk).
                env = {
                    "page": page,
                    "context": context,
                    "browser": browser,
                    "asyncio": asyncio,
                }
                try:
                    # Support async : on enveloppe dans une coroutine.
                    wrapped = (
                        "async def _jarvis_pw_task():\n"
                        + "\n".join("    " + line for line in script.splitlines())
                    )
                    loc: dict = {}
                    exec(wrapped, env, loc)
                    await loc["_jarvis_pw_task"]()
                    result_msg = "Script navigateur exécuté."
                except Exception as e:
                    result_msg = f"Script navigateur a échoué : {e}"
                await browser.close()
                return result_msg

            await browser.close()
            return "Rien à faire : ni URL ni script fournis."
    except Exception as e:
        return f"Playwright erreur : {e}"


# ── Intent fast-path pour "ouvre tel site" ────────────────────────────────

def parse_open_url_intent(texte: str) -> Optional[str]:
    """Heuristique légère : tire un URL ou un nom de site évident.

    Ex: "ouvre youtube" -> https://youtube.com
    """
    t = (texte or "").lower()
    SITES = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "github": "https://github.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
        "linkedin": "https://www.linkedin.com",
        "amazon": "https://www.amazon.fr",
        "leboncoin": "https://www.leboncoin.fr",
    }
    for name, url in SITES.items():
        if f"ouvre {name}" in t or f"va sur {name}" in t:
            return url
    return None
