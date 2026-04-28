from PHOEBUS.skills.registry import skill
from PHOEBUS import google_services as _google
import asyncio

@skill(
    "read_emails",
    risk="medium",
    help_text="Lit vos derniers emails Gmail",
    describe=lambda _: "Lire vos derniers emails Gmail"
)
async def read_emails(data: dict):
    return await asyncio.to_thread(_google.lire_emails)

@skill(
    "write_email",
    risk="high",
    help_text="Envoie un email via Gmail",
    describe=lambda d: f"Envoyer un email à {d.get('recipient')} (Sujet: {d.get('subject')})"
)
async def write_email(data: dict):
    to = data.get("recipient")
    sub = data.get("subject", "Message de PHOEBUS")
    body = data.get("body", "")
    if not to or not body:
        return "Il me manque le destinataire ou le corps du message."
    return await asyncio.to_thread(_google.envoyer_email, to, sub, body)

@skill(
    "read_calendar",
    risk="medium",
    help_text="Affiche votre agenda Google",
    describe=lambda _: "Consulter votre agenda Google"
)
async def read_calendar(data: dict):
    return await asyncio.to_thread(_google.lire_calendrier)

@skill(
    "create_doc",
    risk="medium",
    help_text="Crée un document Google Doc",
    describe=lambda d: f"Créer le Google Doc : {d.get('title')}"
)
async def create_doc(data: dict):
    title = data.get("title", "Nouveau Document")
    content = data.get("content", "")
    return await asyncio.to_thread(_google.creer_google_doc, title, content)

@skill(
    "write_doc",
    risk="medium",
    help_text="Modifie ou ajoute du texte dans un document Google Doc",
    describe=lambda _: "Modifier un document Google"
)
async def skill_write_doc(data: dict):
    content = data.get("content", "")
    return await asyncio.to_thread(_google.modifier_google_doc, content)

@skill(
    "create_sheet",
    risk="medium",
    help_text="Crée une nouvelle feuille Google Sheet",
    describe=lambda d: f"Créer la feuille Google Sheet : {d.get('title')}"
)
async def skill_create_sheet(data: dict):
    title = data.get("title", "Nouvelle Feuille")
    return await asyncio.to_thread(_google.creer_google_sheet, title)
