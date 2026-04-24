# jarvis/google_services.py
"""Google Docs, Gmail, Calendar, Sheets — services Google de JARVIS."""
import os
import pickle
import webbrowser
import base64
from email.mime.text import MIMEText
from datetime import datetime, timezone

from jarvis.config import (
    SCOPES, InstalledAppFlow, GoogleRequest, google_build,
)
import jarvis.state as state


import threading

_google_creds_lock = threading.Lock()
_last_noninteractive_auth_warning = 0.0

def get_google_creds(interactive=True):
    global _last_noninteractive_auth_warning
    if not InstalledAppFlow or not GoogleRequest:
        print("[GOOGLE] Dependances Google absentes - fonctions Google desactivees.")
        return None
    
    with _google_creds_lock:
        creds = None
        if os.path.exists("token.pickle"):
            with open("token.pickle", "rb") as f:
                creds = pickle.load(f)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(GoogleRequest())
                except Exception as e:
                    print(f"[GOOGLE] Erreur refresh token : {e}")
                    creds = None
            
            if not creds or not creds.valid:
                if not os.path.exists("credentials.json"):
                    print("[GOOGLE] Pas de credentials.json - fonctions Google desactivees.")
                    return None
                if not interactive:
                    # Les tâches proactives ne doivent jamais lancer un serveur OAuth
                    # en arrière-plan. Elles réessaieront plus tard.
                    import time
                    now = time.time()
                    if now - _last_noninteractive_auth_warning > 300:
                        print("[GOOGLE] Auth requise : lancez une action Google manuelle pour reconnecter Calendar.")
                        _last_noninteractive_auth_warning = now
                    return None
                flow  = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                # On force le mode 'offline' pour obtenir un Refresh Token longue durée.
                creds = flow.run_local_server(
                    port=0,
                    access_type='offline', 
                    prompt='consent'
                )
            with open("token.pickle", "wb") as f:
                pickle.dump(creds, f)
        return creds


def get_docs_service():
    creds = get_google_creds()
    return google_build("docs", "v1", credentials=creds) if creds and google_build else None


def get_drive_service():
    creds = get_google_creds()
    return google_build("drive", "v3", credentials=creds) if creds and google_build else None


def get_gmail_service():
    creds = get_google_creds()
    return google_build("gmail", "v1", credentials=creds) if creds and google_build else None


def get_sheets_service():
    creds = get_google_creds()
    return google_build("sheets", "v4", credentials=creds) if creds and google_build else None


def get_calendar_service(interactive=True):
    creds = get_google_creds(interactive=interactive)
    return google_build("calendar", "v3", credentials=creds) if creds and google_build else None


def creer_google_doc(titre="Nouveau Document", contenu=""):
    try:
        service = get_docs_service()
        if not service:
            return "Google Docs non disponible."
        doc    = service.documents().create(body={"title": titre}).execute()
        doc_id = doc["documentId"]
        state.dernier_doc_id    = doc_id
        state.dernier_doc_titre = titre
        if contenu:
            requests_body = [{"insertText": {"location": {"index": 1}, "text": contenu}}]
            service.documents().batchUpdate(documentId=doc_id, body={"requests": requests_body}).execute()
        webbrowser.open(f"https://docs.google.com/document/d/{doc_id}/edit")
        return f"Document {titre} cree et ouvert, Floriace."
    except Exception as e:
        return f"Erreur Google Docs : {e}"


def modifier_google_doc(contenu, doc_id=None):
    try:
        service   = get_docs_service()
        if not service:
            return "Google Docs non disponible."
        target_id = doc_id or state.dernier_doc_id
        if not target_id:
            return "Aucun document ouvert en memoire."
        doc       = service.documents().get(documentId=target_id).execute()
        end_index = doc["body"]["content"][-1]["endIndex"] - 1
        requests_body = [{"insertText": {"location": {"index": end_index}, "text": "\n" + contenu}}]
        service.documents().batchUpdate(documentId=target_id, body={"requests": requests_body}).execute()
        webbrowser.open(f"https://docs.google.com/document/d/{target_id}/edit")
        return f"Texte ajoute dans le document {state.dernier_doc_titre}."
    except Exception as e:
        return f"Erreur modification doc : {e}"


def lire_emails(max_results=3):
    try:
        service  = get_gmail_service()
        if not service:
            return "Gmail non disponible."
        results  = service.users().messages().list(userId="me", maxResults=max_results, labelIds=["INBOX"]).execute()
        messages = results.get("messages", [])
        if not messages:
            return "Aucun email trouve."
        reponse = ""
        for msg in messages:
            m       = service.users().messages().get(userId="me", id=msg["id"], format="metadata").execute()
            headers = {h["name"]: h["value"] for h in m["payload"]["headers"]}
            reponse += f"De: {headers.get('From','?')} | Sujet: {headers.get('Subject','?')}\n"
        return reponse.strip()
    except Exception as e:
        return f"Erreur Gmail : {e}"


def envoyer_email(destinataire, sujet, corps):
    try:
        service = get_gmail_service()
        if not service:
            return "Gmail non disponible."
        message = MIMEText(corps)
        message['to'] = destinataire
        message['subject'] = sujet
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        return f"Email envoyé à {destinataire}, Floriace."
    except Exception as e:
        return f"Erreur envoi email : {e}"


def lister_evenements_calendar():
    try:
        service = get_calendar_service()
        if not service:
            return "Google Calendar non disponible."
        now    = datetime.now(timezone.utc).isoformat()
        events = service.events().list(calendarId="primary", timeMin=now,
                                        maxResults=5, singleEvents=True,
                                        orderBy="startTime").execute()
        items = events.get("items", [])
        if not items:
            return "Aucun evenement a venir."
        reponse = ""
        for e in items:
            start    = e["start"].get("dateTime", e["start"].get("date"))
            reponse += f"{start} : {e['summary']}\n"
        return reponse.strip()
    except Exception as e:
        return f"Erreur Calendar : {e}"


def creer_google_sheet(titre="Nouvelle Feuille"):
    try:
        service  = get_sheets_service()
        if not service:
            return "Google Sheets non disponible."
        sheet    = service.spreadsheets().create(body={"properties": {"title": titre}}).execute()
        sheet_id = sheet["spreadsheetId"]
        webbrowser.open(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
        return f"Feuille {titre} creee et ouverte."
    except Exception as e:
        return f"Erreur Google Sheets : {e}"


def lister_evenements_prochains(minutes_avant: int = 15) -> list:
    """Renvoie les événements Google Calendar qui démarrent dans `minutes_avant` minutes.

    Chaque élément est un dict :
      {id, titre, debut (datetime), debut_str (str HH:MM), lieu, description}

    Utilisé par le moteur proactif pour les rappels de RDV.
    """
    try:
        from datetime import timedelta
        service = get_calendar_service(interactive=False)
        if not service:
            return []
        now      = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(minutes=minutes_avant + 1)).isoformat()
        events   = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        items = events.get("items", [])
        result = []
        for e in items:
            start_raw = e["start"].get("dateTime") or e["start"].get("date", "")
            try:
                # Parse ISO 8601
                start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                # N'annoncer que si l'événement commence dans [minutes_avant-2, minutes_avant+1] min
                delta = (start_dt - now).total_seconds() / 60
                if not (minutes_avant - 2 <= delta <= minutes_avant + 1):
                    continue
                debut_str = start_dt.strftime("%Hh%M")
            except Exception:
                debut_str = start_raw
                start_dt  = None
            result.append({
                "id":          e.get("id", ""),
                "titre":       e.get("summary", "Événement"),
                "debut":       start_dt,
                "debut_str":   debut_str,
                "lieu":        e.get("location", ""),
                "description": e.get("description", ""),
            })
        return result
    except Exception as e:
        print(f"[CALENDAR] Erreur lister_evenements_prochains : {e}")
        return []
