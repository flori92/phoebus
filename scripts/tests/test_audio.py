import asyncio
from PHOEBUS.ai import demander_ia
from PHOEBUS.voice import parler
import pygame

async def test():
    print("Demande IA...")
    rep = await demander_ia("bonjour, teste ta voix")
    print(f"Reponse: {rep}")
    print("Parler...")
    await parler(rep)
    print("Fin parler.")

asyncio.run(test())
