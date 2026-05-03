from PHOEBUS.skills.registry import skill
from PHOEBUS import vision as _vision
from PHOEBUS import camera as _camera
import asyncio
import PHOEBUS.state as state

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
    return await _camera.analyser_image(img, question=q, use_arena_for_complex=bool(data.get("deep")))

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
    return await _camera.analyser_image(img, question=q, use_arena_for_complex=bool(data.get("deep")))

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
    return await _camera.analyser_image(img, question=q)

@skill(
    "voir_camera",
    risk="low",
    help_text="Utilise une caméra spécifique pour observer",
    describe=lambda d: f"Regarder via la caméra {d.get('source', 'pc')}"
)
async def skill_voir_camera(data: dict):
    ins = data.get("instruction", "Que vois-tu devant toi ?")
    src = data.get("source", "pc")
    return await _vision.voir_camera(ins, src)

@skill(
    "identifier_objet",
    risk="low",
    help_text="Identifie un objet devant la caméra",
    describe=lambda d: f"Identifier un objet via {d.get('source', 'pc')}"
)
async def skill_identifier_objet(data: dict):
    src = data.get("source", "pc")
    return await _vision.identifier_objet(src)

@skill(
    "lire_texte",
    risk="low",
    help_text="Effectue une lecture OCR sur l'image caméra",
    describe=lambda d: f"Lire le texte via {d.get('source', 'pc')}"
)
async def skill_lire_texte(data: dict):
    src = data.get("source", "pc")
    return await _vision.lire_texte_objet(src)

@skill(
    "identifier_personne",
    risk="low",
    help_text="Reconnaît la personne devant la caméra",
    describe=lambda d: f"Identifier la personne via {d.get('source', 'pc')}"
)
async def skill_identifier_personne(data: dict):
    src = data.get("source", "pc")
    return await _vision.identifier_personne(src)

@skill(
    "vision_tv_ecran",
    risk="low",
    help_text="Analyse ce qui est affiché sur l'écran de la télévision",
    describe=lambda d: f"Analyser l'écran TV (Question: {d.get('question')})"
)
async def vision_tv_ecran(data: dict):
    q = data.get("question") or data.get("instruction") or "Que vois-tu sur la TV ? (YouTube, Netflix, etc.)"
    img = await _camera.capturer_tv_ecran()
    if not img: return "Je n'ai pas pu récupérer l'image de l'écran TV. Vérifie si elle est allumée et connectée en ADB."
    return await _camera.analyser_image(img, question=q, use_arena_for_complex=bool(data.get("deep")))

@skill(
    "voir_ecran",
    risk="high",
    help_text="Prend une capture d'écran et effectue une action visuelle",
    describe=lambda d: f"Analyser l'écran pour : {d.get('instruction')}"
)
async def skill_voir_ecran(data: dict):
    ins = data.get("instruction", "").lower()
    if not ins: return "Aucune instruction pour l'écran."
    
    # Rediriger vers la TV si mentionnée
    if any(k in ins for k in ("tv", "télé", "tele", "tcl", "télévision")):
        return await vision_tv_ecran(data)
        
    return await _vision.PHOEBUS_vision_cliquer(ins)

@skill(
    "vision_ecrire",
    risk="high",
    help_text="Écrit du texte dans une zone de l'écran",
    describe=lambda d: f"Écrire '{d.get('texte')}' sur l'écran"
)
async def skill_vision_ecrire(data: dict):
    ins = data.get("instruction", "")
    txt = data.get("texte", "")
    if not ins or not txt: return "Instruction ou texte manquant."
    return await _vision.PHOEBUS_vision_ecrire(ins, txt)

@skill(
    "proactive_help",
    risk="low",
    help_text="Analyse l'écran pour proposer une aide proactive",
    describe=lambda _: "Analyse proactive de l'écran"
)
async def skill_proactive_help(data: dict):
    state.is_proactive = True
    await state.send_web_state("proactive")
    res = await _vision.analyse_contexte_ecran()
    state.is_proactive = False
    if not res:
        await state.send_web_state("idle")
    return res
