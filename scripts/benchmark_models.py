import asyncio
import time
import sys
import os

# Ajout de la racine au PYTHONPATH pour trouver PHOEBUS
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PHOEBUS.ai import (
    demander_gemini, demander_groq, demander_openai, 
    demander_mistral, demander_kimi, demander_arena, demander_ollama
)
from PHOEBUS.config import OLLAMA_MODELS, GROQ_MODEL, OPENAI_MODEL

async def test_provider(name, func, prompt="Donne moi uniquement la reponse : 2+2=?", is_local=False):
    print(f"Testing {name:.<20}", end="", flush=True)
    start = time.perf_counter()
    try:
        if name == "arena":
            # Arena needs a dummy profile to avoid resolving complex defaults
            from PHOEBUS.brain_router import BrainProfile
            prof = BrainProfile(kind="command", priority="fast", timeout_s=60.0)
            res = await asyncio.wait_for(func(prompt, profile=prof), timeout=65.0)
        else:
            res = await asyncio.wait_for(func(prompt), timeout=60.0)
        
        latency = (time.perf_counter() - start) * 1000
        
        if res:
            status = f"OK ({latency:.0f}ms)"
            color = "\033[92m" if latency < 1000 else "\033[93m"
        else:
            status = "FAILED (Empty)"
            latency = 99999
            color = "\033[91m"
    except Exception as e:
        latency = 99999
        status = f"ERROR: {type(e).__name__}"
        color = "\033[91m"
        
    print(f"{color}{status}\033[0m")
    return name, latency, is_local

async def main():
    print("==================================================")
    print("       PHOEBUS 3.0 - BENCHMARK INTELLIGENCE       ")
    print("==================================================")
    
    # Liste des tests
    tests = [
        ("groq (Cloud Fast)", demander_groq, False),
        ("gemini (Cloud Opt)", demander_gemini, False),
        ("openai (Cloud Smart)", demander_openai, False),
        ("mistral (Cloud)", demander_mistral, False),
        ("kimi (Cloud)", demander_kimi, False),
        ("arena (Cloud Deep)", demander_arena, False),
        (f"ollama ({OLLAMA_MODELS[0] if OLLAMA_MODELS else 'local'})", demander_ollama, True),
    ]
    
    results = []
    for name, func, is_local in tests:
        name, lat, loc = await test_provider(name, func, is_local=is_local)
        results.append({"name": name, "latency": lat, "local": loc})
        
    print("\n--- CLASSEMENT PAR VITESSE ---")
    results.sort(key=lambda x: x["latency"])
    for i, r in enumerate(results):
        lat_str = f"{r['latency']:.0f}ms" if r['latency'] < 99999 else "KO"
        loc_str = "[LOCAL]" if r['local'] else "[CLOUD]"
        print(f"{i+1}. {r['name']:<25} : {lat_str:>8} {loc_str}")

if __name__ == "__main__":
    asyncio.run(main())
