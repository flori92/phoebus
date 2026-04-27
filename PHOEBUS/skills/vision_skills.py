from PHOEBUS.skills.registry import skill
from PHOEBUS import vision as _vision
import asyncio

@skill(
    "vision_camera_pc",
    risk="low",
    help_text="Analyse ce que voit la webcam de l'ordinateur",
    describe=lambda d: f"Analyser l'image de la webcam (Question: {d.get('question', 'que vois-tu')})"
)
async def vision_camera_pc(data: dict):
    q = data.get("question") or data.get("instruction") or "Décris ce que tu vois."
    img = await _vision.capturer_pc_webcam()
    if not img: return "Échec de l'accès à la webcam."
    return await _vision.analyser_image(img, question=q, use_arena_for_complex=bool(data.get("deep")))

@skill(
    "vision_camera_phone",
    risk="low",
    help_text="Demande une photo au smartphone pour analyse",
    describe=lambda d: f"Analyser l'image du téléphone (Question: {d.get('question')})"
)
async def vision_camera_phone(data: dict):
    q = data.get("question") or data.get("instruction") or "Décris ce que tu vois."
    facing = data.get("facing", "environment")
    img = await _vision.capturer_telephone(facing=facing)
    if not img: return "Le smartphone n'a pas répondu à la demande de capture."
    return await _vision.analyser_image(img, question=q, use_arena_for_complex=bool(data.get("deep")))

@skill(
    "vision_camera_ip",
    risk="low",
    help_text="Analyse le flux d'une caméra réseau IP",
    describe=lambda d: f"Analyser la caméra IP {d.get('label') or d.get('url')}"
)
async def vision_camera_ip(data: dict):
    q = data.get("question") or "Décris ce que tu vois."
    url = data.get("url") or ""
    img = await _vision.capturer_ip_camera(url=url)
    if not img: return "Impossible de récupérer l'image de la caméra réseau."
    return await _vision.analyser_image(img, question=q)
