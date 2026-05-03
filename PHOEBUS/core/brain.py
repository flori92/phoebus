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
        
        # --- NOUVELLE ARCHITECTURE PARALLÈLE ---
        workflow.set_entry_point("analyze_intent")
        
        def should_act(state: PhoebusState):
            if state.get("intent") == "CONVERSATION":
                return "generate_response"
            return "plan_action"

        workflow.add_conditional_edges(
            "analyze_intent",
            should_act,
            {
                "generate_response": "generate_response",
                "plan_action": "retrieve_memory"
            }
        )
        
        workflow.add_edge("retrieve_memory", "plan_action")
        workflow.add_edge("plan_action", "execute_action")
        workflow.add_edge("execute_action", "generate_response")
        workflow.add_edge("generate_response", "learn")
        workflow.add_edge("learn", END)
        
        return workflow.compile()
    
    async def analyze_intent(self, state: PhoebusState):
        """Comprend exactement ce que l'utilisateur veut (Mode Turbo)"""
        instruction = (
            "Analyse l'intention de l'utilisateur. "
            "Catégories: SYSTEM_CONTROL, NETWORK, NOTES, VISION, CODE, RESEARCH, CONVERSATION, FILE_MANAGEMENT, AUTOMATION, SECURITY. "
            "Réponds UNIQUEMENT en JSON: {\"intent\": \"...\", \"sub_intent\": \"...\"}"
        )
        
        # --- PRIORITÉ GROQ POUR LA VITESSE ---
        from PHOEBUS.ai import demander_groq, demander_ia
        try:
            # On tente Groq en premier (ultra-rapide)
            resp = await asyncio.wait_for(demander_groq(f"{instruction}\n\nRequête: {state['user_input']}"), timeout=2.0)
        except:
            # Fallback sur le routeur IA standard
            try:
                resp = await asyncio.wait_for(demander_ia(f"{instruction}\n\nRequête: {state['user_input']}"), timeout=3.0)
            except:
                resp = "{}"

        try:
            if "{" in resp:
                raw_json = resp[resp.find("{"):resp.rfind("}")+1]
                intent_data = json.loads(raw_json)
                state["intent"] = intent_data.get("intent", "CONVERSATION")
                state["sub_intent"] = intent_data.get("sub_intent", "")
        except:
            state["intent"] = "CONVERSATION"
        
        # Optimization: lancer la recherche mémoire en tâche de fond immédiatement
        state["_memory_task"] = asyncio.create_task(self._async_retrieve_memory(state["user_input"]))
        return state

    async def _async_retrieve_memory(self, query: str):
        from PHOEBUS.core.memory.long_term import LongTermMemory
        try:
            ltm = LongTermMemory()
            return ltm.search(query, top_k=3)
        except:
            return []

    async def retrieve_memory(self, state: PhoebusState):
        """Récupère les souvenirs (attend la tâche de fond)"""
        task = state.get("_memory_task")
        if task:
            state["memory_relevant"] = await task
        else:
            state["memory_relevant"] = await self._async_retrieve_memory(state["user_input"])
        return state
    
    async def plan_action(self, state: PhoebusState):
        """Planifie les étapes à exécuter"""
        if state["intent"] == "CONVERSATION":
            state["plan"] = []
            return state

        tools_doc = """
        OUTILS DISPONIBLES :
        - 'system' : get_system_info, open_app, close_app, mac_set_volume, mac_dark_mode_toggle
        - 'vision' : what_is_in_my_hand(source='pc'), see_and_describe(source='pc')
        - 'note'   : add_note(content, title), search_notes(query), log_daily(content)
        - 'file'   : list_dir(path), read_file(path), write_file(path, content)
        - 'research': search_web(query), deep_research(topic)
        - 'security': locate_phone, trigger_alarm, emergency_lock # Pour la sécurité mobile
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
        """Génère la réponse finale basée sur les résultats (Mode Turbo)"""
        # Si c'est une simple conversation, on demande une réponse directe sans contexte lourd
        from PHOEBUS.ai import demander_groq, demander_ia
        
        if state["intent"] == "CONVERSATION":
            try:
                resp = await asyncio.wait_for(demander_groq(state["user_input"]), timeout=4.0)
            except:
                resp = await demander_ia(state["user_input"])
            state["final_response"] = resp
            return state

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
