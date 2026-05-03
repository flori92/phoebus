"""Plugin d'exemple — montre comment ajouter une action sans toucher au cœur.

Ce fichier commence par `_` donc il est IGNORÉ par l'auto-découverte
(évite qu'il soit branché par accident). Renomme-le pour t'en servir
de base.
"""
from PHOEBUS.skills import skill
from PHOEBUS.voice import parler


@skill(
    "exemple_dis_bonjour",
    risk="low",
    help="Plugin d'exemple : dit bonjour à un nom donné.",
    describe=lambda data: f"saluer {data.get('nom', 'tout le monde')}",
)
async def dis_bonjour(data):
    nom = data.get("nom") or "tout le monde"
    await parler(f"Bonjour {nom}, ravi de te voir !")
