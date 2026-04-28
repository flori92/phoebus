"""Recherche augmentée pour PHOEBUS — Wikipedia, Wolfram, GitHub, RSS.

Quand le LLM ne sait pas (cutoff de connaissance), PHOEBUS interroge des
sources structurées rapides au lieu d'inventer.

Sources :
- **Wikipedia** (FR par défaut) : API REST publique, pas de clé. Idéal
  pour les questions factuelles "qui est X", "qu'est-ce que Y".
- **Wolfram Alpha** : si `WOLFRAM_APP_ID` configuré. Calculs scientifiques,
  conversions, données chiffrées.
- **GitHub Code Search** : si `GITHUB_TOKEN` configuré. "trouve un exemple
  de X en Python".
- **RSS feeds** : actualités fraîches via feeds définis dans
  `PHOEBUS_RSS_FEEDS` (CSV d'URLs).

Action exposée : `knowledge_query` qui dispatche sur la meilleure source
selon le type de question.
"""
import asyncio
import os
import re
import urllib.parse
from typing import List, Optional

import requests

from PHOEBUS.observability import measure


WIKIPEDIA_LANG = os.getenv("WIKIPEDIA_LANG", "fr").strip() or "fr"
WOLFRAM_APP_ID = os.getenv("WOLFRAM_APP_ID", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
RSS_FEEDS = [
    u.strip() for u in os.getenv(
        "PHOEBUS_RSS_FEEDS",
        "https://www.lemonde.fr/rss/une.xml,https://www.france24.com/fr/rss"
    ).split(",") if u.strip()
]


# ── Wikipedia ────────────────────────────────────────────────────────────

def wikipedia_summary(query: str, lang: str = "") -> str:
    """Résumé court d'un sujet via Wikipedia REST. Retourne texte ou ''."""
    if not query:
        return ""
    use_lang = (lang or WIKIPEDIA_LANG).strip() or "fr"
    title = urllib.parse.quote(query.strip().replace(" ", "_"))
    url = f"https://{use_lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        r = requests.get(url, timeout=4, headers={"Accept": "application/json"})
        if r.status_code == 404:
            # Recherche tolérante : essai via OpenSearch puis ré-appel.
            search_url = (
                f"https://{use_lang}.wikipedia.org/w/api.php"
                f"?action=opensearch&limit=1&format=json"
                f"&search={urllib.parse.quote(query)}"
            )
            sr = requests.get(search_url, timeout=4)
            if sr.status_code == 200:
                arr = sr.json()
                if isinstance(arr, list) and len(arr) > 1 and arr[1]:
                    new_title = urllib.parse.quote(arr[1][0].replace(" ", "_"))
                    r = requests.get(
                        f"https://{use_lang}.wikipedia.org/api/rest_v1/page/summary/{new_title}",
                        timeout=4,
                    )
        if r.status_code != 200:
            return ""
        data = r.json()
        if data.get("type") == "disambiguation":
            return f"Ambiguïté : {data.get('extract', '')[:300]}"
        return (data.get("extract") or "").strip()
    except Exception as e:
        print(f"[KNOW] Wikipedia KO : {e}")
        return ""


# ── Wolfram Alpha ────────────────────────────────────────────────────────

def wolfram_short_answer(query: str) -> str:
    """Endpoint "Short Answers" de Wolfram. Renvoie texte court ou ''."""
    if not WOLFRAM_APP_ID or not query:
        return ""
    url = "https://api.wolframalpha.com/v1/result"
    params = {"i": query, "appid": WOLFRAM_APP_ID, "units": "metric"}
    try:
        r = requests.get(url, params=params, timeout=6)
        if r.status_code == 200 and r.text:
            return r.text.strip()
    except Exception as e:
        print(f"[KNOW] Wolfram KO : {e}")
    return ""


# ── GitHub code search ──────────────────────────────────────────────────

def github_code_search(query: str, lang: str = "python", per_page: int = 3) -> str:
    """Recherche du code public sur GitHub. Renvoie un mini résumé."""
    if not query:
        return ""
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    q = f"{query} language:{lang}" if lang else query
    url = "https://api.github.com/search/code"
    try:
        r = requests.get(
            url, params={"q": q, "per_page": per_page},
            headers=headers, timeout=8,
        )
        if r.status_code == 401:
            return "GitHub a refusé : configure GITHUB_TOKEN dans .env."
        if r.status_code != 200:
            return ""
        items = (r.json() or {}).get("items", [])
        if not items:
            return f"Pas de code trouvé pour « {query} »."
        lignes = [f"Trouvé {len(items)} extrait(s) sur GitHub :"]
        for it in items:
            repo = (it.get("repository") or {}).get("full_name", "?")
            path = it.get("path", "?")
            url = it.get("html_url", "")
            lignes.append(f"  {repo} : {path}\n    {url}")
        return "\n".join(lignes)
    except Exception as e:
        return f"GitHub KO : {e}"


# ── RSS news feeds ──────────────────────────────────────────────────────

def latest_news(max_per_feed: int = 3) -> str:
    """Concatène les derniers titres des feeds configurés."""
    if not RSS_FEEDS:
        return "Aucun flux RSS configuré (PHOEBUS_RSS_FEEDS)."
    lignes = []
    for feed in RSS_FEEDS:
        try:
            r = requests.get(feed, timeout=5,
                             headers={"User-Agent": "PhoebusBot/1.0"})
            if r.status_code != 200:
                continue
            text = r.text
            # Parser minimaliste sans dépendance : on extrait <title> + <item>.
            titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", text, flags=re.DOTALL)
            # Le 1er title est celui du feed lui-même, on saute.
            heads = [t.strip() for t in titles[1 : 1 + max_per_feed] if t.strip()]
            if heads:
                feed_label = feed.split("/")[2]
                lignes.append(f"[{feed_label}]")
                lignes.extend(f"  - {h}" for h in heads)
        except Exception:
            continue
    return "\n".join(lignes) if lignes else "Aucune actualité récupérable."


# ── Dispatcher : choisit la bonne source pour la question ───────────────

def _looks_like_calc(q: str) -> bool:
    t = (q or "").lower()
    if re.search(r"[+\-*/^=]\s*\d|\d\s*[+\-*/^]", q):
        return True
    keywords = ("convertis", "convertir", "combien font", "combien fait",
                "calcule", "résous", "résoudre", "intégrale", "dérivée",
                "taux", "monnaie", "distance entre")
    return any(k in t for k in keywords)


def _looks_like_news(q: str) -> bool:
    t = (q or "").lower()
    return any(k in t for k in (
        "actualité", "actualités", "news", "dernières nouvelles",
        "qu'est-ce qui se passe", "quoi de neuf",
    ))


def _looks_like_code(q: str) -> bool:
    t = (q or "").lower()
    return any(k in t for k in (
        "exemple de code", "comment coder", "snippet", "github", "open source",
        "fonction python", "exemple python", "exemple javascript",
    ))


async def query(question: str) -> str:
    """Dispatch automatique selon la nature de la question."""
    if not question:
        return ""

    async with measure("knowledge.query"):
        # 1. Calcul → Wolfram en premier (si dispo), sinon Wikipedia.
        if _looks_like_calc(question) and WOLFRAM_APP_ID:
            ans = await asyncio.to_thread(wolfram_short_answer, question)
            if ans:
                return ans

        # 2. Actualités → RSS.
        if _looks_like_news(question):
            return await asyncio.to_thread(latest_news)

        # 3. Code → GitHub.
        if _looks_like_code(question):
            return await asyncio.to_thread(github_code_search, question)

        # 4. Par défaut → Wikipedia.
        ans = await asyncio.to_thread(wikipedia_summary, question)
        if ans:
            return ans

        # Dernier recours Wolfram.
        if WOLFRAM_APP_ID:
            return await asyncio.to_thread(wolfram_short_answer, question)

    return ""
