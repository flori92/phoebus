# phoebus/agents/orchestrator.py
import asyncio

class AgentOrchestrator:
    def __init__(self):
        # On importera les agents ici pour éviter les imports circulaires
        pass

    async def execute(self, step: dict) -> dict:
        """Route une étape du plan vers l'agent approprié"""
        tool = step.get("tool", "").lower()
        action = step.get("action", "")
        params = step.get("params", {})

        print(f"[ORCHESTRATOR] Routage: {tool}.{action}")

        if "system" in tool:
            from PHOEBUS.agents.system_agent import SystemAgent
            agent = SystemAgent()
            # On tente de mapper l'action à une méthode
            method = getattr(agent, action, agent.execute_command)
            if method == agent.execute_command:
                return method(params.get("command") or action)
            return method(**params)

        if "network" in tool:
            from PHOEBUS.connectors.wifi_controller import NetworkController
            agent = NetworkController()
            method = getattr(agent, action, None)
            if method:
                return method(**params)

        # Fallback sur les anciens skills PHOEBUS si l'agent n'est pas encore implémenté
        try:
            from PHOEBUS.actions import executer_une_action
            ok, msg = await executer_une_action({"action": action, **params})
            return {"success": ok, "result": msg}
        except:
            return {"success": False, "error": f"Outil {tool} ou action {action} non supporté"}
