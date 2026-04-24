import os
import json
import time
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import google.genai as genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


logging.basicConfig(level=logging.INFO, format="[PHOEBUS_AGENT] %(message)s")

if load_dotenv:
    load_dotenv()


class PHOEBUSAgent:
    """Minimal reusable agent scaffold for the PHOEBUS workspace."""

    def __init__(self,
                 api_key: str = None,
                 model: str = "gemini-2.5-flash",
                 memory_file: str = "phoebus_memoire.json"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model
        self.memory_file = Path(memory_file)
        self.client = genai.Client(api_key=self.api_key) if genai else None
        self.memory = self._load_memory()

    def _load_memory(self) -> dict:
        if self.memory_file.exists():
            try:
                return json.loads(self.memory_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logging.warning("Unable to load memory: %s", exc)
        return {}

    def _save_memory(self) -> None:
        try:
            self.memory_file.write_text(json.dumps(self.memory, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logging.warning("Unable to save memory: %s", exc)

    def remember(self, key: str, value: str) -> None:
        self.memory[key] = {
            "valeur": value,
            "timestamp": time.strftime("%d/%m/%Y %H:%M")
        }
        self._save_memory()

    def forget(self, key: str) -> bool:
        if key in self.memory:
            del self.memory[key]
            self._save_memory()
            return True
        return False

    def memory_context(self) -> str:
        if not self.memory:
            return ""
        lines = ["MEMOIRE PERSISTANTE :"]
        for key, data in self.memory.items():
            lines.append(f"  - {key} : {data['valeur']} (note le {data['timestamp']})")
        return "\n".join(lines)

    def system_prompt(self) -> str:
        base = (
            "Tu es PHOEBUS, assistant IA personnel cree par Floriace.\n"
            "Floriace est ton createur, proprietaire et utilisateur principal.\n"
            "Son objectif est un PHOEBUS portable, securise, local-first, "
            "connecte a Home Assistant et capable d'automatiser la maison.\n"
            "Reponds en francais, de facon directe et pragmatique, avec une "
            "pointe de sarcasme affectueux quand le contexte s'y prete.\n"
            "N'invente jamais son age, sa date de naissance, sa famille, son "
            "adresse ou d'autres informations personnelles.\n\n"
        )
        base += self.memory_context()
        base += (
            "\n\nTu es connecte a Home Assistant, la domotique de Floriace. "
            "Quand Floriace parle de lumieres, prises, chauffage, temperature, "
            "scenes ou alarme, tu DOIS generer une commande JSON. "
            "Pour CES demandes domotiques UNIQUEMENT, reponds avec le JSON.\n"
        )
        return base

    def build_contents(self, user_message: str) -> list:
        return [
            types.Content(role="user", parts=[types.Part(text=user_message)])
        ]

    def generate_response(self, user_message: str) -> str:
        if not self.client or not types:
            raise RuntimeError("google.genai is not installed or failed to import.")

        response = self.client.models.generate_content(
            model=self.model,
            contents=self.build_contents(user_message),
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt(),
                temperature=0.7,
            ),
        )
        return (getattr(response, "text", "") or "").strip()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the PHOEBUS agent scaffold.")
    parser.add_argument("message", nargs="+", help="User message for the agent.")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Model to use.")
    parser.add_argument("--memory-file", default="phoebus_memoire.json", help="Memory file path.")
    args = parser.parse_args()

    agent = PHOEBUSAgent(model=args.model, memory_file=args.memory_file)
    message = " ".join(args.message)
    print("System prompt:\n", agent.system_prompt())
    print("\nUser message:\n", message)

    try:
        response = agent.generate_response(message)
        print("\nAgent response:\n", response)
    except Exception as exc:
        logging.error("Cannot generate response: %s", exc)


if __name__ == "__main__":
    main()
