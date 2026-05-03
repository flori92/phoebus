# PHOEBUS/agents/learning_agent.py
import json
from PHOEBUS.ai import demander_ia
from PHOEBUS.core.memory.long_term import LongTermMemory
from PHOEBUS.agents.notetaking_agent import NoteTakingAgent

class LearningAgent:
    def __init__(self):
        self.memory = LongTermMemory()
        self.notes = NoteTakingAgent()

    async def reflect_and_learn(self, user_input: str, response: str):
        """Analyse l'interaction pour apprendre des choses sur Floriace."""
        prompt = (
            f"Analyse cet échange entre Floriace et PHOEBUS.\n"
            f"Floriace: {user_input}\n"
            f"PHOEBUS: {response}\n"
            "Extrais-en des faits, des préférences, des habitudes ou des rappels.\n"
            "Réponds UNIQUEMENT en JSON: {\"facts\": [], \"preferences\": [], \"habits\": [], \"importance\": 0-10}"
        )
        
        learning_json = await demander_ia(prompt)
        try:
            if "{" in learning_json:
                data = json.loads(learning_json[learning_json.find("{"):learning_json.rfind("}")+1])
                
                # Mémorisation vectorielle
                for fact in data.get("facts", []):
                    self.memory.learn_fact(fact, category="fact")
                for pref in data.get("preferences", []):
                    self.memory.learn_fact(pref, category="preference")
                
                # Si c'est important, on en fait une note Obsidian/SiYuan
                if data.get("importance", 0) > 7:
                    summary = "\n".join(data.get("facts", []) + data.get("preferences", []))
                    await self.notes.log_daily(f"💡 [APPRENTISSAGE AUTONOME] : {summary}")
                
                return {"success": True, "learned": data}
        except Exception as e:
            return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "Rien à apprendre"}

    async def self_improve(self):
        """Analyse ses propres performances et propose des améliorations."""
        # TODO: Implémenter l'analyse des logs et du cache
        pass
