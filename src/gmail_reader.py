import base64
import json
import os

PROCESSED_PATH = "data/processed_ids.json"
SEARCH_QUERY = "has:attachment (filename:pdf OR filename:docx)"


def search_messages(service, query=SEARCH_QUERY, max_results=50):

    ids = []
    request = service.users().messages().list(
        userId="me", q=query, maxResults=min(max_results, 100)
    )
    while request is not None and len(ids) < max_results:
        response = request.execute()
        ids.extend(m["id"] for m in response.get("messages", []))
        request = service.users().messages().list_next(request, response)
    return ids[:max_results]


def get_message(service, msg_id):
    return service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()


def get_header(message, name):
    for h in message["payload"].get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode(data):
    data += "=" * (-len(data) % 4)  
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def extract_body(payload):

    data = payload.get("body", {}).get("data")
    if payload.get("mimeType") == "text/plain" and data:
        return _decode(data)
    for part in payload.get("parts", []):
        text = extract_body(part)
        if text:
            return text
    return ""


def list_attachments(payload):

    found = []
    filename = payload.get("filename")
    body = payload.get("body", {})
    if filename and body.get("attachmentId"):
        found.append({
            "filename": filename,
            "mime_type": payload.get("mimeType"),
            "attachment_id": body["attachmentId"],
            "size": body.get("size", 0),
        })
    for part in payload.get("parts", []):
        found.extend(list_attachments(part))
    return found


def parse_message(message):

    return {
        "id": message["id"],
        "sender": get_header(message, "From"),
        "subject": get_header(message, "Subject"),
        "date": get_header(message, "Date"),
        "body": extract_body(message["payload"]),
        "attachments": list_attachments(message["payload"]),
    }


def load_processed_ids():
    if os.path.exists(PROCESSED_PATH):
        with open(PROCESSED_PATH, "r") as f:
            return set(json.load(f))
    return set()


def save_processed_ids(ids):
    os.makedirs(os.path.dirname(PROCESSED_PATH), exist_ok=True)
    with open(PROCESSED_PATH, "w") as f:
        json.dump(sorted(ids), f, indent=2)