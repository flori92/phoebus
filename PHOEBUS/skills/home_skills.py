from PHOEBUS.skills.registry import skill
from PHOEBUS import home as _home
import asyncio

@skill(
    "ha_lumiere",
    risk="low",
    help_text="Allume ou éteint une lumière",
    describe=lambda d: f"Changer la lumière de {d.get('piece')} en {d.get('etat')}"
)
async def ha_lumiere(data: dict):
    piece = data.get("piece")
    etat = data.get("etat", "on")
    couleur = data.get("couleur")
    luminosite = data.get("luminosite")
    
    ent = _home.resolve_ha_entity("light", piece)
    if _home.ha_lumiere(ent, etat, couleur, luminosite):
        return f"D'accord, j'ai mis la lumière de {piece} sur {etat}."
    return f"Je n'ai pas réussi à contrôler la lumière de {piece}."

@skill(
    "ha_prise",
    risk="low",
    help_text="Allume ou éteint une prise connectée",
    describe=lambda d: f"Changer la prise de {d.get('piece')} en {d.get('etat')}"
)
async def ha_prise(data: dict):
    piece = data.get("piece")
    etat = data.get("etat", "on")
    ent = _home.resolve_ha_entity("switch", piece)
    if _home.ha_prise(ent, etat):
        return f"C'est fait pour la prise de {piece}."
    return f"Échec du contrôle de la prise {piece}."

@skill(
    "ha_thermostat",
    risk="low",
    help_text="Règle la température du thermostat",
    describe=lambda d: f"Régler le thermostat à {d.get('temperature')} degrés"
)
async def ha_thermostat(data: dict):
    t = data.get("temperature", 21)
    ent = _home.resolve_ha_entity("climate", "salon")
    if _home.ha_thermostat(ent, t):
        return f"Thermostat réglé sur {t} degrés."
    return "Impossible de régler le thermostat."

@skill(
    "ha_scene",
    risk="low",
    help_text="Active une scène Home Assistant",
    describe=lambda d: f"Activer la scène {d.get('nom')}"
)
async def ha_scene(data: dict):
    n = data.get("nom", "")
    ent = _home.resolve_scene_entity(n)
    if _home.ha_scene(ent):
        return f"Scène {n} activée."
    return f"Impossible de lancer la scène {n}."
