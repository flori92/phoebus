"""Function calling natif Gemini (hybride, opt-in).

Le flux JSON actuel — le LLM émet des blocs `{"action": "..."}` dans son
texte et on parse à la main — fonctionne mais a des défauts :
- Arguments non typés, le LLM peut envoyer n'importe quoi.
- Parser fragile face aux formatages markdown, guillemets typographiques.
- Pas de validation côté modèle : l'action peut ne pas exister.

Google GenAI supporte `FunctionDeclaration` : on décrit les fonctions
avec un schéma JSON, le modèle renvoie un objet `FunctionCall` typé et
validé. Plus robuste et un peu plus rapide.

On garde les deux chemins : les skills/actions existants sont auto-exposés
comme functions. Activation via env var `JARVIS_USE_FUNCTION_CALLING=1`.
Le fallback JSON-in-text reste la voie par défaut pour la compat Groq/Mistral/
Ollama (qui n'ont pas tous ce format).
"""
import os
from typing import Any, Dict, List, Optional

from PHOEBUS.config import types


ENABLED = os.getenv("JARVIS_USE_FUNCTION_CALLING", "0").strip().lower() in (
    "1", "true", "yes", "on",
)


# Schémas des actions les plus courantes. On pourrait les générer depuis
# le skill registry mais l'introspection de Python n'est pas toujours
# suffisante pour inférer les bons types — on préfère les écrire à la main
# pour les actions stables.
CORE_FUNCTION_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "ha_lumiere",
        "description": "Allume ou éteint une lumière dans une pièce de la maison.",
        "parameters": {
            "type": "object",
            "properties": {
                "piece": {"type": "string", "description": "Pièce ciblée (salon, cuisine, chambre...)"},
                "etat": {"type": "string", "enum": ["on", "off"], "description": "État désiré"},
                "luminosite": {"type": "integer", "description": "0-255, optionnel"},
            },
            "required": ["piece", "etat"],
        },
    },
    {
        "name": "ha_thermostat",
        "description": "Règle le thermostat à une température donnée.",
        "parameters": {
            "type": "object",
            "properties": {
                "temperature": {"type": "number", "description": "En degrés Celsius"},
            },
            "required": ["temperature"],
        },
    },
    {
        "name": "meteo",
        "description": "Donne la météo actuelle pour une ville.",
        "parameters": {
            "type": "object",
            "properties": {
                "ville": {"type": "string", "description": "Nom de la ville, vide = par défaut"},
            },
        },
    },
    {
        "name": "timer_set",
        "description": "Programme un minuteur ou un rappel.",
        "parameters": {
            "type": "object",
            "properties": {
                "duration_s": {"type": "integer", "description": "Durée en secondes"},
                "label": {"type": "string", "description": "Description courte (optionnel)"},
                "kind": {"type": "string", "enum": ["timer", "rappel"], "description": "timer court ou rappel différé"},
            },
            "required": ["duration_s"],
        },
    },
    {
        "name": "send_email",
        "description": "Envoie un email via Gmail. ACTION SENSIBLE — demandera confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Adresse email du destinataire"},
                "subject": {"type": "string"},
                "body": {"type": "string", "description": "Corps du message en texte brut"},
                "cc": {"type": "string"},
                "bcc": {"type": "string"},
            },
            "required": ["to", "body"],
        },
    },
    {
        "name": "memoriser",
        "description": "Enregistre une information clé/valeur en mémoire persistante.",
        "parameters": {
            "type": "object",
            "properties": {
                "cle": {"type": "string"},
                "valeur": {"type": "string"},
            },
            "required": ["cle", "valeur"],
        },
    },
    {
        "name": "recherche_web",
        "description": "Effectue une recherche web.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "media_recommendations",
        "description": "Recommande un film, une serie ou un documentaire et ouvre une plateforme VOD legale.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["film", "serie", "documentaire"]},
                "genre": {"type": "string", "description": "comedie, action, thriller, horreur, science-fiction..."},
                "platform": {"type": "string", "description": "justwatch, netflix, prime, disney, canal, youtube"},
                "open": {"type": "boolean", "description": "Ouvrir la plateforme dans le navigateur"},
            },
        },
    },
    {
        "name": "agent_planifie",
        "description": "Lance l'agent planificateur pour une tâche complexe multi-étapes.",
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "Description détaillée de l'objectif"},
            },
            "required": ["instruction"],
        },
    },
]


def build_tools() -> Optional[list]:
    """Construit l'objet `tools` à passer à Gemini. Renvoie None si indisponible."""
    if not ENABLED or not types:
        return None
    try:
        # API Google GenAI : types.Tool(function_declarations=[...])
        function_declarations = []
        for schema in CORE_FUNCTION_SCHEMAS:
            function_declarations.append(
                types.FunctionDeclaration(
                    name=schema["name"],
                    description=schema["description"],
                    parameters=schema["parameters"],
                )
            )
        return [types.Tool(function_declarations=function_declarations)]
    except Exception as e:
        print(f"[FC] Construction tools impossible : {e}")
        return None


def extract_function_calls(response) -> List[Dict[str, Any]]:
    """Extrait la liste de function calls d'une réponse Gemini.

    Renvoie une liste de {action, args} prête à passer au dispatcher.
    """
    calls: List[Dict[str, Any]] = []
    if response is None:
        return calls
    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if content is None:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            fc = getattr(part, "function_call", None)
            if fc is None:
                continue
            name = getattr(fc, "name", None)
            args = getattr(fc, "args", None) or {}
            if isinstance(args, dict):
                payload = dict(args)
            else:
                # Certaines versions renvoient un proto → cast via dict()
                try:
                    payload = dict(args)
                except Exception:
                    payload = {}
            if name:
                payload["action"] = name
                calls.append(payload)
    return calls
