import base64
import json
import os
import re

PROCESSED_PATH = "data/processed_ids.json"
SEARCH_QUERY = "has:attachment (filename:pdf OR filename:docx)"

CV_DIR = "data/cvs"
SUPPORTED_EXTENSIONS = (".pdf", ".docx")
MAGIC_BYTES = {".pdf": b"%PDF", ".docx": b"PK"}



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
    if filename and (body.get("attachmentId") or body.get("data")):
        found.append({
            "filename": filename,
            "mime_type": payload.get("mimeType"),
            "attachment_id": body.get("attachmentId"),
            "inline_data": body.get("data"),
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



def is_supported(attachment):

    return attachment["filename"].lower().endswith(SUPPORTED_EXTENSIONS)


def download_attachment(service, message_id, attachment_id):

    att = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    data = att["data"]
    data += "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data)


def attachment_content(service, message_id, attachment):
    data = attachment.get("inline_data")
    if data:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return download_attachment(service, message_id, attachment["attachment_id"])


def safe_filename(name):

    name = os.path.basename(name)
    return re.sub(r"[^\w.\- ]", "_", name)


def save_cv_attachments(service, email):

    os.makedirs(CV_DIR, exist_ok=True)
    saved = []

    for att in email["attachments"]:
        if not is_supported(att):
            print(f"  Ignored (unsupported type): {att['filename']}")
            continue

        try:
            content = attachment_content(service, email["id"], att)

            ext = os.path.splitext(att["filename"].lower())[1]
            if not content.startswith(MAGIC_BYTES[ext]):
                print(f"  Ignored (content doesn't match {ext}): {att['filename']}")
                continue


            path = os.path.join(CV_DIR, f"{email['id']}_{safe_filename(att['filename'])}")
            with open(path, "wb") as f:
                f.write(content)
            saved.append(path)

        except Exception as e:
            print(f"  Failed to download {att['filename']}: {e}")

    return saved
