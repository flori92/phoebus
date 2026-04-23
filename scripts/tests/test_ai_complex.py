import asyncio
from jarvis.ai import demander_ia
async def test():
    rep = await demander_ia("Parle moi de la France et de sa capitale.")
    print(f"Reponse: {rep}")
asyncio.run(test())
