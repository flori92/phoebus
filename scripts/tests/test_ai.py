import asyncio
from jarvis.ai import demander_ia
async def test():
    rep = await demander_ia("bonjour")
    print(f"Reponse: {rep}")
asyncio.run(test())
