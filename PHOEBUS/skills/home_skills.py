from PHOEBUS.skills.registry import skill
from PHOEBUS import home as _home
import asyncio
import os

@skill(
    "ha_lumiere",
    risk="low",
    help_text="Allume ou éteint une lumière",
    describe=lambda d: f"Changer la lumière de {d.get('piece')} en {d.get('etat')}"
)
async def ha_lumiere(data: dict):
    piece = data.get("piece", "salon")
    etat = data.get("etat", "on")
    couleur = data.get("couleur")
    luminosite = data.get("luminosite")
    
    from PHOEBUS.home import PIECES_LUMIERES
    ent = _home.resolve_ha_entity("light", piece, PIECES_LUMIERES, default_prefix="light")
    if _home.ha_lumiere(ent, etat, luminosite=luminosite, rgb=couleur):
        return f"D'accord, j'ai mis la lumière de {piece} sur {etat}."
    return f"Je n'ai pas réussi à contrôler la lumière de {piece}."

@skill(
    "ha_prise",
    risk="low",
    help_text="Allume ou éteint une prise connectée",
    describe=lambda d: f"Changer la prise de {d.get('piece')} en {d.get('etat')}"
)
async def ha_prise(data: dict):
    piece = data.get("piece", "salon")
    etat = data.get("etat", "on")
    from PHOEBUS.home import PIECES_PRISES
    ent = _home.resolve_ha_entity("switch", piece, PIECES_PRISES, default_prefix="switch")
    if _home.ha_interrupteur(ent, etat):
        return f"C'est fait pour la prise de {piece}."
    return f"Échec du contrôle de la prise {piece}."

@skill(
    "ha_temperature",
    risk="low",
    help_text="Donne la température d'une pièce",
    describe=lambda d: f"Vérifier la température dans {d.get('piece', 'le salon')}"
)
async def ha_temperature(data: dict):
    piece = data.get("piece", "salon")
    ent = _home.resolve_temperature_sensor(piece)
    val = _home.ha_get_etat(ent)
    if val != "inconnu":
        return f"Il fait {val} degrés dans {piece}."
    return f"Je ne trouve pas de capteur de température pour {piece}."

@skill(
    "ha_humidite",
    risk="low",
    help_text="Donne le taux d'humidité d'une pièce",
    describe=lambda d: f"Vérifier l'humidité dans {d.get('piece', 'le salon')}"
)
async def ha_humidite(data: dict):
    piece = data.get("piece", "salon")
    ent = _home.resolve_humidity_sensor(piece)
    val = _home.ha_get_etat(ent)
    if val != "inconnu":
        return f"Le taux d'humidité dans {piece} est de {val}%."
    return f"Capteur d'humidité introuvable pour {piece}."

@skill(
    "ha_batterie",
    risk="low",
    help_text="Donne le niveau de batterie d'un appareil",
    describe=lambda d: f"Vérifier la batterie de {d.get('appareil', 'mon téléphone')}"
)
async def ha_batterie(data: dict):
    appareil = data.get("appareil", "mon téléphone")
    ent = _home.resolve_battery_sensor(appareil)
    val = _home.ha_get_etat(ent)
    if val != "inconnu":
        return f"La batterie de {appareil} est à {val}%."
    return f"Impossible de trouver le niveau de batterie pour {appareil}."

@skill(
    "ha_energie",
    risk="low",
    help_text="Donne la consommation d'énergie d'un appareil",
    describe=lambda d: f"Vérifier la consommation de {d.get('appareil', 'tv')}"
)
async def ha_energie(data: dict):
    appareil = data.get("appareil", "tv")
    ent = _home.resolve_energy_sensor(appareil)
    val = _home.ha_get_etat(ent)
    if val != "inconnu":
        try:
            from PHOEBUS.home import HA_TARIFS
            kwh = float(val)
            cout = round(kwh * HA_TARIFS.get("p1", 0.22), 2)
            return f"La consommation est de {kwh} kWh, soit environ {cout} euros."
        except ValueError:
            return f"La consommation est de {val} kWh."
    return f"Capteur d'énergie introuvable pour {appareil}."

@skill(
    "ha_alarme",
    risk="high",
    help_text="Active ou désactive l'alarme",
    describe=lambda d: f"Changer l'alarme en mode {d.get('etat', 'on')}"
)
async def ha_alarme(data: dict):
    etat = data.get("etat", "on")
    ent = _home.resolve_alarm_entity()
    service = "alarm_arm_away" if etat == "on" else "alarm_disarm"
    if _home.ha_appeler_service("alarm_control_panel", service, ent):
        return f"L'alarme a été mise sur {etat}."
    return "Erreur lors du changement d'état de l'alarme."

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

@skill(
    "ha_aspirateur",
    risk="low",
    help_text="Contrôle l'aspirateur robot",
    describe=lambda d: f"Envoyer l'ordre {d.get('commande', 'nettoyage')} à l'aspirateur"
)
async def ha_aspirateur(data: dict):
    cmd = data.get("commande", "start").lower()
    ent = _home.resolve_vacuum_entity()
    srv_map = {
        "start": "start", "demarre": "start", "nettoie": "start",
        "stop": "stop", "arrete": "stop",
        "pause": "pause",
        "base": "return_to_base", "rentre": "return_to_base"
    }
    srv = srv_map.get(cmd, "start")
    if _home.ha_appeler_service("vacuum", srv, ent):
        return f"L'ordre '{cmd}' a été envoyé à l'aspirateur."
    return "Je n'ai pas pu communiquer avec l'aspirateur."
