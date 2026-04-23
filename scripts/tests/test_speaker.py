import asyncio
from jarvis.voice import parler
async def test():
    print("Test de la synthèse vocale...")
    await parler("Ceci est un test pour vérifier le haut parleur.")
    print("Terminé.")
asyncio.run(test())
