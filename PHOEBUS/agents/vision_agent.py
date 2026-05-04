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

    async def analyze_image(self, image_path: str, query: str = None):
        """Analyse une image spécifique (ex: reçue via Telegram) avec OCR."""
        import os
        if not os.path.exists(image_path):
            return {"success": False, "error": f"Fichier introuvable : {image_path}"}
        
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        
        # Prompt enrichi pour l'OCR et la reconnaissance précise
        vision_prompt = (
            f"Analyse cette image avec précision. {query if query else ''}\n"
            "1. Identifie l'objet principal.\n"
            "2. LIS TOUT LE TEXTE visible (OCR).\n"
            "3. Décris les détails importants (marque, couleur, état)."
        )
        
        description = await analyser_image(img_bytes, vision_prompt)
        return {"success": True, "description": description}

    # Aliases pour le routage plus flexible
    async def describe_hand(self, **kwargs): return await self.what_is_in_my_hand(**kwargs)
    async def describe_room(self, **kwargs): return await self.see_and_describe(**kwargs)
