# PHOEBUS/main.py
import asyncio
import sys
import os
from rich.console import Console
from rich.panel import Panel

# Ajout du dossier racine au PATH pour permettre les imports croisés
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PHOEBUS.core.brain import PhoebusBrain
from PHOEBUS.interfaces.voice.voice_interface import VoiceInterface
from PHOEBUS.agents.system_agent import SystemAgent
from PHOEBUS.core.memory.long_term import LongTermMemory

console = Console()

class Phoebus:
    def __init__(self):
        self.brain = PhoebusBrain()
        self.voice = VoiceInterface()
        self.system = SystemAgent()
        self.memory = LongTermMemory()
        self.running = True
    
    async def boot(self):
        """Séquence de démarrage PHOEBUS v2"""
        console.print(Panel.fit(
            "[bold cyan]⚡ PHOEBUS v2.0 - Système IA Personnel[/bold cyan]\n"
            "[dim]Initialisation du Cerveau Multi-Agents...[/dim]",
            border_style="cyan"
        ))
        
        info = self.system.get_system_info()
        console.print(f"  ✅ [bold]OS:[/bold] {info['os']}")
        console.print(f"  ✅ [bold]CPU:[/bold] {info['cpu_percent']}%")
        console.print(f"  ✅ [bold]RAM:[/bold] {info['ram']['used_percent']}%")
        
        # On ne parle au boot que si on n'est pas en mode muet
        if os.getenv("PHOEBUS_MUTE") != "1":
            await self.voice.speak("Bonjour Monsieur. Phoebus v2 est en ligne. Tous les systèmes de raisonnement sont opérationnels.")
    
    async def run_text_mode(self):
        """Mode terminal interactif"""
        await self.boot()
        console.print("\n[dim]Entrez 'quit' pour sortir.[/dim]")
        
        while self.running:
            try:
                user_input = console.input("\n[bold green]Floriace > [/bold green]")
                
                if user_input.lower() in ["quit", "exit", "bye"]:
                    await self.voice.speak("Au revoir Monsieur. Phoebus se met en veille.")
                    break
                
                if not user_input.strip():
                    continue
                
                # Le cerveau réfléchit via le graphe de raisonnement
                response = await self.brain.think(user_input)
                console.print(f"\n[bold cyan]Phoebus >[/bold cyan] {response}")
                
                # Mémorisation
                self.memory.remember_conversation(user_input, response)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[bold red]Erreur:[/bold red] {e}")

if __name__ == "__main__":
    p = Phoebus()
    asyncio.run(p.run_text_mode())
