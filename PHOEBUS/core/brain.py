# phoebus/core/brain.py
import json
import asyncio
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END

# On importe les outils existants de PHOEBUS
try:
    from PHOEBUS.ai import demander_ia
    from PHOEBUS.rag_memory import stocker_souvenir
    import PHOEBUS.state as state
except ImportError:
    # Fallback pour le développement initial
    async def demander_ia(q): return "Service IA indisponible"
    def stocker_souvenir(m): pass

class PhoebusState(TypedDict):
    user_input: str
    intent: str
    sub_intent: str
    context: list
    memory_relevant: list
    plan: list
    current_step: int
    results: list
    final_response: str
    confidence: float

class PhoebusBrain:
    def __init__(self):
        self.system_prompt = self._build_system_prompt()
        self.graph = self._build_reasoning_graph()
    
    def _build_system_prompt(self):
        return """Tu es PHOEBUS, un assistant IA personnel ultra-avancé.
        
        Tu es l'équivalent de JARVIS pour ton créateur Floriace.
        
        Tes capacités :
        - Contrôle total des machines (Mac et PC) via commandes système
        - Gestion du réseau WiFi et des appareils connectés
        - Prise de notes et PKM (Obsidian, SiYuan)
        - Vision par ordinateur (caméra, détection d'objets)
        - Apprentissage autonome et auto-amélioration
        - Exécution de code Python, Shell, AppleScript, PowerShell
        - Recherche web avancée et analyse de données
        - Mémoire à long terme de toutes les interactions
        - Anticipation des besoins de l'utilisateur
        
        Ton style :
        - Précis, efficace, légèrement sophistiqué
        - Tu tutoies Floriace et l'appelles par son prénom.
        - Tu es proactif : tu suggères des améliorations
        - Tu es honnête quand tu ne sais pas
        - Tu demandes confirmation avant toute action destructive
        """
    
    def _build_reasoning_graph(self):
        """Graphe de raisonnement multi-étapes via LangGraph"""
        workflow = StateGraph(PhoebusState)
        
        workflow.add_node("analyze_intent", self.analyze_intent)
        workflow.add_node("retrieve_memory", self.retrieve_memory)
        workflow.add_node("plan_action", self.plan_action)
        workflow.add_node("execute_action", self.execute_action)
        workflow.add_node("generate_response", self.generate_response)
        workflow.add_node("learn", self.learn)
        
        workflow.add_edge("analyze_intent", "retrieve_memory")
        workflow.add_edge("retrieve_memory", "plan_action")
        workflow.add_edge("plan_action", "execute_action")
        workflow.add_edge("execute_action", "generate_response")
        workflow.add_edge("generate_response", "learn")
        workflow.add_edge("learn", END)
        
        workflow.set_entry_point("analyze_intent")
        
        return workflow.compile()
    
    async def analyze_intent(self, state: PhoebusState):
        """Comprend exactement ce que l'utilisateur veut"""
        instruction = (
            "Analyse l'intention de l'utilisateur. "
            "Catégories: SYSTEM_CONTROL, NETWORK, NOTES, VISION, CODE, RESEARCH, CONVERSATION, FILE_MANAGEMENT, AUTOMATION. "
            "Réponds UNIQUEMENT en JSON: {\"intent\": \"...\", \"sub_intent\": \"...\", \"entities\": [], \"urgency\": \"low/high\"}"
        )
        # On utilise le cerveau IA existant
        resp = await demander_ia(f"{instruction}\n\nRequête: {state['user_input']}")
        try:
            # On nettoie le JSON si l'IA a ajouté du texte
            if "{" in resp:
                raw_json = resp[resp.find("{"):resp.rfind("}")+1]
                intent_data = json.loads(raw_json)
                state["intent"] = intent_data.get("intent", "CONVERSATION")
                state["sub_intent"] = intent_data.get("sub_intent", "")
        except:
            state["intent"] = "CONVERSATION"
        return state
    
    async def retrieve_memory(self, state: PhoebusState):
        """Récupère les souvenirs pertinents (RAG)"""
        from PHOEBUS.core.memory.long_term import LongTermMemory
        try:
            ltm = LongTermMemory()
            state["memory_relevant"] = ltm.search(state["user_input"], top_k=3)
        except:
            state["memory_relevant"] = []
        return state
    
    async def plan_action(self, state: PhoebusState):
        """Planifie les étapes à exécuter"""
        if state["intent"] == "CONVERSATION":
            state["plan"] = []
            return state

        tools_doc = """
        OUTILS DISPONIBLES :
        - 'system' : get_system_info, open_app, close_app, mac_set_volume, mac_dark_mode_toggle
        - 'vision' : what_is_in_my_hand(source='pc'/'phone'), see_and_describe(source='pc'/'phone')
        - 'note'   : add_note(content, title), search_notes(query), log_daily(content)
        - 'file'   : list_dir(path), read_file(path), write_file(path, content)
        - 'research': search_web(query), deep_research(topic)
        """

        instruction = (
            f"Planifie l'exécution. Intent: {state['intent']}. Mémoire: {state['memory_relevant']}\n"
            f"{tools_doc}\n"
            "Réponds UNIQUEMENT en JSON: {\"steps\": [{\"action\": \"NOM_METHODE\", \"tool\": \"NOM_OUTIL\", \"params\": {}, \"risk_level\": \"low\"}]}"
        )
        resp = await demander_ia(f"{instruction}\n\nRequête: {state['user_input']}")
        try:
            if "{" in resp:
                raw_json = resp[resp.find("{"):resp.rfind("}")+1]
                state["plan"] = json.loads(raw_json).get("steps", [])
        except:
            state["plan"] = []
        return state
    
    async def execute_action(self, state: PhoebusState):
        """Exécute chaque étape du plan via l'orchestrateur d'agents"""
        from PHOEBUS.agents.orchestrator import AgentOrchestrator
        orchestrator = AgentOrchestrator()
        
        results = []
        for step in state["plan"]:
            if step.get("risk_level", "low") == "high":
                results.append({"status": "NEEDS_CONFIRMATION", "step": step})
            else:
                try:
                    result = await orchestrator.execute(step)
                    results.append(result)
                except Exception as e:
                    results.append({"status": "ERROR", "error": str(e)})
        
        state["results"] = results
        return state

    async def generate_response(self, state: PhoebusState):
        """Génère la réponse finale basée sur les résultats"""
        context = f"Intent: {state['intent']}\nResults: {state['results']}\nMemory: {state['memory_relevant']}"
        resp = await demander_ia(f"Génère une réponse finale pour Floriace.\nContext: {context}\nRequête: {state['user_input']}")
        state["final_response"] = resp
        return state

    async def learn(self, state: PhoebusState):
        """Phase d'apprentissage autonome post-interaction"""
        from PHOEBUS.agents.learning_agent import LearningAgent
        learner = LearningAgent()
        await learner.reflect_and_learn(state["user_input"], state["final_response"])
        return state
    
    async def think(self, user_input: str) -> str:
        """Point d'entrée principal pour le raisonnement"""
        initial_state: PhoebusState = {
            "user_input": user_input,
            "intent": "",
            "sub_intent": "",
            "context": [],
            "memory_relevant": [],
            "plan": [],
            "current_step": 0,
            "results": [],
            "final_response": "",
            "confidence": 0.0
        }
        
        try:
            final_state = await self.graph.ainvoke(initial_state)
            return final_state["final_response"]
        except Exception as e:
            print(f"[BRAIN] Erreur reasoning graph : {e}")
            # Fallback sur l'IA directe
            return await demander_ia(user_input)
