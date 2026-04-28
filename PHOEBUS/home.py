# PHOEBUS/home.py
"""Home Assistant — entités, résolution, météo, sport, énergie."""
import time
import requests
from datetime import datetime

from PHOEBUS.config import (
    HA_URL, HA_TOKEN, HA_HEADERS, SERPAPI_API_KEY, YOUTUBE_API_KEY,
    CODES_METEO, VILLE_PAR_DEFAUT, LAT_PAR_DEFAUT, LON_PAR_DEFAUT,
    client, types, CHOSEN_MODEL,
)
from PHOEBUS.utils import normalize_text
from PHOEBUS.security import DEVICE_CONFIG

# ── Cache états HA ──────────────────────────────────────────────────────────
HA_STATES_CACHE = {"ts": 0, "states": []}

# ── Maps d'entités (fallback historiques) ──────────────────────────────────
PIECES_LUMIERES = {
    "salon": "light.salon", "plafond salon": "light.plafond",
    "canapes": "light.canapes", "lampadaire": "light.lampadaire",
    "lampe de chevet": "light.lampe_de_chevet_2",
    "grosse boule": "light.grosse_boule", "petite boule": "light.petite_boule",
    "cuisine": "light.lsc_smart_led_strip_rgbic_cctic_5m",
    "cuisine 2": "light.cuisine_2",
    "esteban": "light.pc_3", "pc esteban": "light.pc_3",
    "bureau": "light.bureau", "pc": "light.pc", "pc 2": "light.pc_2",
    "parents": "light.chambre_parentale",
    "chambre parentale": "light.chambre_parentale",
    "chambre": "light.chambre_parentale",
    "plafond chambre": "light.plafond_2",
    "toutes": "light.all", "tout": "light.all",
}

PIECES_PRISES = {
    "salon": "switch.prise_salon", "bureau": "switch.prise_bureau",
    "cuisine": "switch.prise_cuisine",
}

PIECES_CAPTEURS = {
    "salon": "sensor.salon_temperature_2",
    "chambre": "sensor.miaomiaoc_de_blt_4_14kc52pmcgk00_t2_temperature_p_2_1",
    "bureau": "sensor.temp_temperature",
    "exterieur": "sensor.temperature_exterieure",
    "dehors": "sensor.temperature_exterieure",
    "consommation": "sensor.lixee_zlinky_tic_puissance_apparente",
    "tiktok": "sensor.tiktok_followers_techenclair",
    "oeufs": "input_select.ramassage_des_oeufs",
}

PIECES_HUMIDITE = {"bureau": "sensor.temp_humidite"}

HA_TARIFS = {"p1": 0.1296, "p2": 0.1603, "p3": 0.1486,
             "p4": 0.1894, "p5": 0.1568, "p6": 0.7562}

APPAREILS_ENERGIE = {
    "tv": "sensor.prise_1_salon_mensuel", "salon": "sensor.prise_1_salon_mensuel",
    "pc esteban": "sensor.prise_3_pc_esteban_mensuel",
    "esteban": "sensor.prise_3_pc_esteban_mensuel",
    "zoe": "sensor.zoe_mensuel", "voiture": "sensor.zoe_mensuel",
    "lave-vaisselle": "sensor.prise_2_lave_vaisselle_mensuel",
    "pc salon": "sensor.pc_salon_conso_pc_salon_mensuel_2",
    "bureau": "sensor.bureau_mensuel",
}

APPAREILS_BATTERIE = {
    "mon telephone": "sensor.sm_s921b_battery_level",
    "papa": "sensor.sm_s921b_battery_level",
    "floriace": "sensor.sm_s921b_battery_level",
    "samsung papa": "sensor.sm_s921b_battery_level",
    "julie": "sensor.sm_julie_battery_level",
    "maman": "sensor.sm_julie_battery_level",
    "samsung maman": "sensor.sm_julie_battery_level",
    "esteban": "sensor.esteban_battery_level",
    "honor": "sensor.honor_battery_level",
    "tablette honor": "sensor.honor_battery_level",
    "montre papa": "sensor.galaxy_watch6_classic_d4he_battery_level",
    "montre floriace": "sensor.galaxy_watch6_classic_d4he_battery_level",
    "montre maman": "sensor.galaxy_watch8_fbxh_battery_level",
    "montre julie": "sensor.galaxy_watch8_fbxh_battery_level",
    "bob": "sensor.bob_batterie", "aspirateur bob": "sensor.bob_batterie",
    "dyad": "sensor.dyad_air_2024_batterie",
    "aspirateur dyad": "sensor.dyad_air_2024_batterie",
    "telecommande hue": "sensor.maison_interrupteur_batterie",
    "interrupteur": "sensor.maison_interrupteur_batterie",
    "toner": "sensor.samsung_m2020_series_black_toner_s_n_crum_17091625519",
    "imprimante": "sensor.samsung_m2020_series_black_toner_s_n_crum_17091625519",
    "boite aux lettres": "sensor.detecterur_batterie",
    "detecteur cuisine": "sensor.detecteur_1_batterie",
    "detecteur escalier": "sensor.detecteur_2_batterie",
    "camera jardin": "sensor.arriere_cour_battery_percentage",
    "thermometre bureau": "sensor.temp_batterie",
}

THESPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"


# ── Résolution d'entités ───────────────────────────────────────────────────

def get_config_alias(domain, name):
    aliases = DEVICE_CONFIG.get("aliases", {})
    domain_aliases = aliases.get(domain, {})
    key = normalize_text(name)
    for alias, entity_id in domain_aliases.items():
        if normalize_text(alias) == key:
            return entity_id
    return None


def ha_get_states_cached(max_age=30):
    now = time.time()
    if HA_STATES_CACHE["states"] and now - HA_STATES_CACHE["ts"] < max_age:
        return HA_STATES_CACHE["states"]
    if not HA_URL or not HA_TOKEN or HA_TOKEN in ["VOTRE_TOKEN_ICI", "VOTRE_API"] or "url-home-assitant" in HA_URL.lower():
        return []
    try:
        r = requests.get(f"{HA_URL}/api/states", headers=HA_HEADERS, timeout=6)
        r.raise_for_status()
        states = r.json()
        HA_STATES_CACHE["states"] = states
        HA_STATES_CACHE["ts"] = now
        return states
    except Exception as e:
        # On affiche l'erreur seulement si on n'a rien en cache pour éviter le spam
        if not HA_STATES_CACHE["states"]:
            print(f"[HA] Home Assistant injoignable ({HA_URL}). Vérifiez votre configuration.")
        return HA_STATES_CACHE["states"] or []


def entity_label(entity):
    attrs = entity.get("attributes", {}) if isinstance(entity, dict) else {}
    return " ".join([
        entity.get("entity_id", ""),
        attrs.get("friendly_name", ""),
        attrs.get("device_class", ""),
    ])


def discover_entity(domain, query, required_terms=None):
    query_norm = normalize_text(query)
    required_terms = [normalize_text(t) for t in (required_terms or []) if t]
    for entity in ha_get_states_cached():
        entity_id = entity.get("entity_id", "")
        if not entity_id.startswith(f"{domain}."):
            continue
        label = normalize_text(entity_label(entity))
        if query_norm and query_norm not in label:
            continue
        if any(term not in label for term in required_terms):
            continue
        return entity_id
    return None


def resolve_ha_entity(domain, name, fallback_map=None, required_terms=None, default_prefix=None):
    name = str(name or "").strip().lower()
    configured = get_config_alias(domain, name)
    if configured:
        return configured
    if fallback_map and name in fallback_map:
        return fallback_map[name]
    discovered = discover_entity(domain, name, required_terms=required_terms)
    if discovered:
        return discovered
    return f"{default_prefix or domain}.{name.replace(' ', '_')}" if name else None


def resolve_temperature_sensor(piece):
    return (get_config_alias("sensor", f"temperature {piece}") or
            PIECES_CAPTEURS.get(str(piece).lower()) or
            discover_entity("sensor", piece, required_terms=["temperature"]))


def resolve_humidity_sensor(piece):
    return (get_config_alias("sensor", f"humidite {piece}") or
            PIECES_HUMIDITE.get(str(piece).lower()) or
            discover_entity("sensor", piece, required_terms=["humid"]))


def resolve_battery_sensor(appareil):
    return (get_config_alias("sensor", f"batterie {appareil}") or
            APPAREILS_BATTERIE.get(str(appareil).lower()) or
            discover_entity("sensor", appareil, required_terms=["battery"]))


def resolve_energy_sensor(appareil):
    return (get_config_alias("sensor", f"energie {appareil}") or
            APPAREILS_ENERGIE.get(str(appareil).lower()) or
            discover_entity("sensor", appareil, required_terms=["kwh"]))


def resolve_scene_entity(nom):
    return (get_config_alias("scene", nom) or
            discover_entity("scene", nom) or
            (f"scene.{str(nom).strip().lower().replace(' ', '_')}" if nom else None))


def resolve_alarm_entity(name="alarme"):
    return (get_config_alias("alarm_control_panel", name) or
            discover_entity("alarm_control_panel", name) or
            "alarm_control_panel.home_base_2")


def resolve_vacuum_entity(name="bob"):
    return (get_config_alias("vacuum", name) or
            discover_entity("vacuum", name) or
            "vacuum.bob")


# ── Résumé contextuel HA pour injection dans le prompt ─────────────────────

# Domaines qu'on expose au LLM. Les autres (sensor, binary_sensor...) sont
# nombreux et rarement utilisés en commande directe → on les masque.
_HA_EXPOSED_DOMAINS = (
    "light", "switch", "scene", "climate", "vacuum",
    "media_player", "cover", "lock", "fan",
    "alarm_control_panel", "script", "input_boolean",
)


def resume_ha_context(max_per_domain=18):
    """Produit un résumé compact des entités HA disponibles, à injecter
    dans le prompt système. Renvoie '' si HA indisponible ou vide.

    Format :
        ENTITÉS HOME ASSISTANT :
        - light : Plafond salon, Cuisine, Bureau, Chambre parentale (+3 autres)
        - switch : Prise salon, Prise bureau
        - scene : Cinéma, Soirée, Lecture
        ...
    """
    states = ha_get_states_cached()
    if not states:
        return ""

    by_domain = {}
    for s in states:
        eid = s.get("entity_id", "")
        if "." not in eid:
            continue
        dom = eid.split(".", 1)[0]
        if dom not in _HA_EXPOSED_DOMAINS:
            continue
        friendly = (s.get("attributes", {}) or {}).get("friendly_name") or eid
        by_domain.setdefault(dom, []).append(friendly)

    if not by_domain:
        return ""

    lignes = [
        "ENTITÉS HOME ASSISTANT DISPONIBLES (réfère-toi à ces noms exacts dans tes commandes JSON) :"
    ]
    for dom in _HA_EXPOSED_DOMAINS:
        if dom not in by_domain:
            continue
        items = sorted(set(by_domain[dom]))
        extra = max(0, len(items) - max_per_domain)
        shown = items[:max_per_domain]
        suffix = f" (+{extra} autres)" if extra else ""
        lignes.append(f"- {dom} : {', '.join(shown)}{suffix}")

    return "\n".join(lignes)


def prewarm_ha_context():
    """Force un appel HA au démarrage pour peupler le cache, sans bloquer."""
    try:
        ha_get_states_cached(max_age=0)
    except Exception as e:
        print(f"[HA] prewarm échoué : {e}")


# ── Services HA ────────────────────────────────────────────────────────────

def ha_appeler_service(domaine, service, entity_id, donnees=None):
    try:
        payload = {"entity_id": entity_id}
        if donnees:
            payload.update(donnees)
        print(f"[HA DEBUG] Calling {domaine}/{service} for {entity_id} with {donnees}")
        r = requests.post(f"{HA_URL}/api/services/{domaine}/{service}",
                          headers=HA_HEADERS, json=payload, timeout=5)
        print(f"[HA DEBUG] Response {r.status_code}: {r.text}")
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"[HA] Erreur service : {e}")
        return False


def ha_get_etat(entity_id, attribut=None):
    if not HA_URL or "url-home-assitant" in HA_URL.lower() or HA_TOKEN == "VOTRE_API":
        return "inconnu"
    try:
        r    = requests.get(f"{HA_URL}/api/states/{entity_id}", headers=HA_HEADERS, timeout=5)
        data = r.json()
        if attribut:
            return data.get("attributes", {}).get(attribut, "inconnu")
        return data.get("state", "inconnu")
    except Exception:
        # Silencieux pour ne pas spammer les logs
        return "inconnu"


def ha_get_calendrier(entity_id):
    try:
        now   = datetime.now()
        start = now.strftime("%Y-%m-%dT00:00:00Z")
        end   = now.strftime("%Y-%m-%dT23:59:59Z")
        r = requests.get(f"{HA_URL}/api/calendars/{entity_id}",
                          headers=HA_HEADERS, params={"start": start, "end": end}, timeout=5)
        return r.json()
    except Exception as e:
        print(f"[HA] Erreur calendrier : {e}")
        return []


def ha_lumiere(entity_id, etat="on", luminosite=None, rgb=None):
    service_name = "toggle" if etat == "toggle" else ("turn_on" if etat == "on" else "turn_off")
    donnees = {}
    if etat == "on":
        if luminosite is not None:
            donnees["brightness"] = int(luminosite)
        if rgb is not None:
            donnees["rgb_color"] = rgb
    return ha_appeler_service("light", service_name, entity_id, donnees)


def ha_interrupteur(entity_id, etat="on"):
    service_name = "turn_on" if etat == "on" else "turn_off"
    return ha_appeler_service("switch", service_name, entity_id)


def ha_thermostat(entity_id, temperature):
    return ha_appeler_service("climate", "set_temperature", entity_id, {"temperature": temperature})


def ha_scene(scene_id):
    return ha_appeler_service("scene", "turn_on", scene_id)


# ── Météo ──────────────────────────────────────────────────────────────────

def geocoder_ville(ville):
    try:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                          params={"name": ville, "count": 1, "language": "fr", "format": "json"}, timeout=5)
        data = r.json()
        if data.get("results"):
            res = data["results"][0]
            return res["latitude"], res["longitude"], res.get("name", ville), res.get("country", "")
    except Exception as e:
        print(f"[METEO] Erreur geocoding : {e}")
    return None, None, ville, ""


def get_meteo_actuelle(ville=None, periode=None):
    try:
        nom_ville = ville or VILLE_PAR_DEFAUT
        lat, lon, nom_affiche, pays = geocoder_ville(nom_ville)
        if lat is None:
            lat, lon = LAT_PAR_DEFAUT, LON_PAR_DEFAUT
            nom_affiche = VILLE_PAR_DEFAUT
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weathercode,precipitation",
            "hourly": "temperature_2m,precipitation_probability",
            "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_sum,wind_speed_10m_max,sunrise,sunset",
            "timezone": "Europe/Paris", "forecast_days": 3, "wind_speed_unit": "kmh",
        }, timeout=8)
        data = r.json()
        cur  = data["current"]
        code = cur.get("weathercode", 0)
        desc = CODES_METEO.get(code, "conditions inconnues")
        temp = round(float(cur.get("temperature_2m", 0)))

        daily = data.get("daily") or {}
        if periode == "journee" and daily.get("temperature_2m_max"):
            temp_max = round(float(daily["temperature_2m_max"][0]))
            temp_min = round(float(daily["temperature_2m_min"][0]))
            pluie = float((daily.get("precipitation_sum") or [0])[0] or 0)
            vent = round(float((daily.get("wind_speed_10m_max") or [0])[0] or 0))
            desc_jour = CODES_METEO.get((daily.get("weathercode") or [code])[0], desc)
            return (
                f"À {nom_affiche} aujourd'hui, le ciel est {desc_jour}. "
                f"Il fait {temp} degrés maintenant, avec {temp_min} à {temp_max} degrés prévus. "
                f"Pluie prévue : {pluie:g} millimètres. Vent maximum : {vent} kilomètres heure."
            )

        return f"À {nom_affiche}, il fait {temp} degrés et le ciel est {desc}."
    except Exception as e:
        print(f"[METEO] Erreur : {e}")
        return "Je n'arrive pas à récupérer la météo pour le moment."


def get_alertes_meteo(ville=None):
    try:
        nom_ville = ville or VILLE_PAR_DEFAUT
        lat, lon, nom_affiche, _ = geocoder_ville(nom_ville)
        if lat is None:
            lat, lon, nom_affiche = LAT_PAR_DEFAUT, LON_PAR_DEFAUT, VILLE_PAR_DEFAUT
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "daily": "weathercode,precipitation_sum,wind_speed_10m_max",
            "timezone": "Europe/Paris", "forecast_days": 3,
        }, timeout=8)
        data  = r.json()
        daily = data["daily"]
        alertes = []
        for i in range(len(daily["weathercode"])):
            code  = daily["weathercode"][i]
            pluie = daily.get("precipitation_sum", [0]*3)[i] or 0
            vent  = daily.get("wind_speed_10m_max", [0]*3)[i] or 0
            jour  = ["aujourd hui", "demain", "apres-demain"][i]
            if code in [95, 96, 99]: alertes.append(f"Orage prevu {jour}")
            if code in [71, 73, 75, 85, 86]: alertes.append(f"Neige prevue {jour}")
            if pluie > 20: alertes.append(f"Fortes pluies {jour} ({pluie}mm)")
            if vent > 60:  alertes.append(f"Vents forts {jour} ({vent} km/h)")
        if alertes:
            return f"Alertes meteo pour {nom_affiche} : " + ", ".join(alertes) + "."
        return f"Aucune alerte meteo pour {nom_affiche} dans les 3 prochains jours."
    except Exception as e:
        return f"Impossible de verifier les alertes meteo : {e}"


# ── Recherche Web ──────────────────────────────────────────────────────────

def recherche_web_serpapi(query):
    if not SERPAPI_API_KEY or SERPAPI_API_KEY == "VOTRE_CLE_ICI":
        return "Floriace, la clé SerpAPI n'est pas configurée dans le fichier d'environnement."
    try:
        print(f"[WEB] Recherche SerpAPI pour : {query}")
        params = {"engine": "google", "q": query, "api_key": SERPAPI_API_KEY, "hl": "fr", "gl": "fr"}
        r = requests.get("https://serpapi.com/search.json", params=params, timeout=10)
        data = r.json()
        if "news_results" in data:
            news = data["news_results"][:3]
            reponse = f"Voici les dernières actualités pour {query} :\n"
            for n in news:
                reponse += f"- {n.get('title', '')} (via {n.get('source', 'Source inconnue')})\n"
            return reponse
        if "organic_results" in data:
            results = data["organic_results"][:3]
            reponse = f"Voici ce que j'ai trouvé sur le web pour {query} :\n"
            for r in results:
                reponse += f"- {r.get('title', '')} : {r.get('snippet', '')}\n"
            return reponse
        return f"Je n'ai rien trouvé de pertinent sur le web pour : {query}."
    except Exception as e:
        print(f"[WEB] Erreur SerpAPI : {e}")
        return "Une erreur est survenue lors de la recherche sur internet."


# ── Sport ──────────────────────────────────────────────────────────────────

def get_resultats_football(equipe=None, ligue=None):
    try:
        if equipe:
            print(f"[SPORT] Recherche pour l'equipe : {equipe}")
            r = requests.get(f"{THESPORTSDB_BASE}/searchteams.php", params={"t": equipe}, timeout=5)
            teams = r.json().get("teams")
            if not teams:
                return f"Je n'ai pas trouvé l'équipe {equipe}."
            team_id   = teams[0]["idTeam"]
            team_name = teams[0]["strTeam"]
            res_last = requests.get(f"{THESPORTSDB_BASE}/eventslast.php", params={"id": team_id}, timeout=5).json()
            res_next = requests.get(f"{THESPORTSDB_BASE}/eventsnext.php", params={"id": team_id}, timeout=5).json()
            matchs_passes = res_last.get("results", [])
            matchs_futurs = res_next.get("events", [])
            reponse = f"Concernant le {team_name} : "
            if matchs_futurs:
                m = matchs_futurs[0]
                reponse += f"Le prochain match aura lieu le {m.get('dateEvent', '?')} à {m.get('strTime', '')} contre {m.get('strOpponent')}. "
            if matchs_passes:
                m = matchs_passes[0]
                reponse += f"Leur dernier résultat était {m.get('intHomeScore')} à {m.get('intAwayScore')} contre {m.get('strOpponent')}."
            if not matchs_futurs and not matchs_passes:
                return f"Je n'ai pas d'informations récentes ou futures pour {team_name}."
            return reponse
        else:
            nom_ligue = ligue or "Ligue 1"
            ligue_ids = {
                "ligue 1": "4334", "premier league": "4328", "liga": "4335",
                "bundesliga": "4331", "serie a": "4332",
                "champions league": "4480", "ligue des champions": "4480",
            }
            ligue_id = ligue_ids.get(nom_ligue.lower(), "4334")
            r = requests.get(f"{THESPORTSDB_BASE}/eventspastleague.php", params={"id": ligue_id}, timeout=5)
            matchs = r.json().get("events", [])
            if not matchs:
                return f"Aucun resultat trouve pour {nom_ligue}."
            reponse = f"Derniers resultats {nom_ligue} : "
            lignes = []
            for m in matchs[-6:]:
                lignes.append(f"{m.get('strHomeTeam','?')} {m.get('intHomeScore','?')}-{m.get('intAwayScore','?')} {m.get('strAwayTeam','?')} ({m.get('dateEvent','?')})")
            return reponse + " | ".join(lignes)
    except Exception as e:
        print(f"[SPORT] Erreur football : {e}")
        return f"Impossible de recuperer les resultats football : {e}"


def get_classement_football(ligue=None):
    try:
        nom_ligue = ligue or "Ligue 1"
        ligue_ids = {
            "ligue 1": "4334", "premier league": "4328", "liga": "4335",
            "bundesliga": "4331", "serie a": "4332",
            "champions league": "4480", "ligue des champions": "4480",
        }
        ligue_id = ligue_ids.get(nom_ligue.lower(), "4334")
        r = requests.get(f"{THESPORTSDB_BASE}/lookuptable.php",
                          params={"l": ligue_id, "s": "2024-2025"}, timeout=8)
        tableau = r.json().get("table", [])
        if not tableau:
            return f"Classement {nom_ligue} non disponible pour le moment."
        reponse = f"Classement {nom_ligue} : "
        lignes = []
        for eq in tableau[:10]:
            lignes.append(f"{eq.get('intRank','?')}. {eq.get('strTeam','?')} - {eq.get('intPoints','?')}pts ({eq.get('intPlayed','?')}J)")
        return reponse + " | ".join(lignes)
    except Exception as e:
        print(f"[SPORT] Erreur classement : {e}")
        return f"Impossible de recuperer le classement : {e}"


def get_resultats_sport_gemini(question_sport):
    if not client or not types:
        return "Le module Gemini n'est pas disponible pour les resultats sportifs en direct."
    try:
        response = client.models.generate_content(
            model=CHOSEN_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=
                f"Donne-moi les derniers resultats et actualites sportives en 2026 "
                f"pour : {question_sport}. "
                f"Sois precis, donne les scores et dates. Reponds en francais."
            )])],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                system_instruction="Tu es un expert sportif. Donne des resultats precis et a jour. Reponds de facon concise et conversationnelle en francais."
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"[SPORT] Erreur Gemini sport : {e}")
        return "Je n arrive pas a recuperer les resultats sportifs pour le moment."


# ── YouTube ────────────────────────────────────────────────────────────────

def chercher_youtube(recherche):
    if not YOUTUBE_API_KEY or YOUTUBE_API_KEY == "VOTRE_CLE_ICI":
        print("[YOUTUBE] Cle API non configuree.")
        return None
    try:
        r   = requests.get("https://www.googleapis.com/youtube/v3/search",
                            params={"part": "snippet", "q": recherche, "type": "video",
                                    "maxResults": 1, "key": YOUTUBE_API_KEY}, timeout=5)
        vid = r.json()["items"][0]["id"]["videoId"]
        return f"https://www.youtube.com/watch?v={vid}"
    except Exception as e:
        print(f"Erreur YouTube : {e}")
        return None
