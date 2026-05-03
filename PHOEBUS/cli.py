"""CLI interactif PHOEBUS — discuter avec lui en terminal sans micro.

Utile :
- pour tester un déploiement sans hardware audio (CI, serveur headless)
- pour les commandes que tu préfères taper (mots de passe, code...)
- pour accompagner un screen capture / screenshot avec une question
- en mode silencieux quand quelqu'un dort à côté

Lance :
    python -m PHOEBUS.cli           → REPL chat
    python -m PHOEBUS.cli "question"  → one-shot

Le CLI réutilise tout : skills, intent fast-path, brain_router, RAG.
La seule différence : la sortie va dans le terminal (printf) au lieu
de la TTS, et l'entrée vient de stdin au lieu du micro.
"""
import argparse
import asyncio
import sys


async def _ask_once(question: str, speak: bool = False) -> str:
    """Pose une question, renvoie la réponse texte. Optionnellement TTS."""
    from PHOEBUS.ai import demander_ia
    from PHOEBUS.actions import traiter_reponse_ia

    rep = await demander_ia(question)

    if not rep:
        return "(aucune réponse)"

    # Si c'est une commande JSON, on l'exécute et on renvoie le résultat
    # de l'action plutôt que le JSON brut. traiter_reponse_ia parle déjà
    # via parler() — en CLI on intercepte pour ne pas spammer.
    if "{" in rep and "}" in rep:
        # On laisse la TTS si demandée, sinon on stocke le résultat.
        if speak:
            await traiter_reponse_ia(rep)
            return ""
        # Mode silencieux : on monkey-patch parler() le temps de l'action.
        import PHOEBUS.voice as voice_mod
        captured: list = []
        original = voice_mod.parler

        async def silent_parler(texte, *args, **kwargs):
            captured.append(texte)

        voice_mod.parler = silent_parler
        try:
            await traiter_reponse_ia(rep)
        finally:
            voice_mod.parler = original
        return "\n".join(captured) if captured else "(action exécutée)"

    if speak:
        from PHOEBUS.voice import parler
        await parler(rep)
    return rep


async def _repl():
    """Boucle interactive type "chat"."""
    print("PHOEBUS CLI — tape ta question. /quit pour sortir, /tts pour activer la voix.\n")
    speak = False
    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line in ("/quit", "/exit", "/q"):
                break
            if line == "/tts":
                speak = not speak
                print(f"  TTS = {speak}")
                continue
            if line == "/help":
                print("  /tts   bascule la synthèse vocale")
                print("  /quit  sortir")
                continue

            try:
                rep = await _ask_once(line, speak=speak)
            except Exception as e:
                print(f"  [ERREUR] {e}")
                continue
            if rep:
                print(f"\n{rep}\n")
    except KeyboardInterrupt:
        pass
    print("\nÀ bientôt, Floriace.")


def main():
    p = argparse.ArgumentParser(
        prog="phoebus-cli",
        description="PHOEBUS en mode terminal (sans micro/enceinte).",
    )
    p.add_argument("question", nargs="*", help="question one-shot")
    p.add_argument("--tts", action="store_true",
                   help="activer aussi la voix (utile sur Mac)")
    args = p.parse_args()

    if args.question:
        question = " ".join(args.question)
        rep = asyncio.run(_ask_once(question, speak=args.tts))
        if rep:
            print(rep)
        return

    asyncio.run(_repl())


if __name__ == "__main__":
    main()
