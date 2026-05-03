# PHOEBUS/agents/vision_agent.py
import asyncio
from PHOEBUS.camera import capturer_pc_webcam, capturer_telephone, analyser_image

class VisionAgent:
    def __init__(self):
        pass

    async def what_is_in_my_hand(self, source: str = "pc"):
        """Analyse ce que l'utilisateur a dans la main."""
        image = None
        if source == "pc":
            image = await capturer_pc_webcam()
        elif source == "phone":
            image = await capturer_telephone()
        
        if not image:
            return {"success": False, "error": "Impossible de capturer l'image."}
        
        description = await analyser_image(image, "Dis-moi exactement ce que tu vois dans la main de l'utilisateur ou devant la caméra.")
        return {"success": True, "description": description}

    async def see_and_describe(self, source: str = "pc"):
        """Description générale de l'environnement."""
        image = None
        if source == "pc":
            image = await capturer_pc_webcam()
        elif source == "phone":
            image = await capturer_telephone()
            
        if not image:
            return {"success": False, "error": "Capture impossible."}
        
        description = await analyser_image(image, "Décris l'environnement actuel en détail.")
        return {"success": True, "description": description}

    # Aliases pour le routage plus flexible
    async def describe_hand(self, **kwargs): return await self.what_is_in_my_hand(**kwargs)
    async def describe_room(self, **kwargs): return await self.see_and_describe(**kwargs)
