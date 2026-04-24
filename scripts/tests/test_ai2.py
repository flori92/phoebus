import asyncio
from PHOEBUS.ai import demander_ia
async def test():
    rep = await demander_ia("Parle moi de la France")
    print(f"Reponse: {rep}")
asyncio.run(test())
