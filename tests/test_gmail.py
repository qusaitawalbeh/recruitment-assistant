import sys
from types import SimpleNamespace
from src import gmail_reader, screening


def test_gmail_batch_dedup_and_independent_errors(client, job, cv_bytes, monkeypatch):
    monkeypatch.setitem(sys.modules, "src.gmail_auth", SimpleNamespace(get_gmail_service=lambda: object()))
    queries = []
    def search(service, query, max_results):
        queries.append(query)
        return ["bad-message", "m1", "m2"]
    monkeypatch.setattr(gmail_reader, "search_messages", search)
    def get_message(service, mid):
        if mid == "bad-message":
            raise RuntimeError("Cannot fetch message")
        return mid
    monkeypatch.setattr(gmail_reader, "get_message", get_message)
    monkeypatch.setattr(gmail_reader, "parse_message", lambda mid: {
        "id": mid, "sender": "test@example.invalid", "subject": "Python application", "attachments": [
            {"filename": "bad.pdf", "attachment_id": "bad", "size": 20},
            {"filename": "cv.docx", "attachment_id": "good", "size": 100},
            {"filename": "photo.png", "attachment_id": "ignored", "size": 100},
        ]})
    content = cv_bytes()
    monkeypatch.setattr(gmail_reader, "download_attachment", lambda service, mid, aid: content if aid == "good" else b"bad")
    result = screening.screen_gmail(job["id"], 'subject:"Python application"')
    assert [r["status"] for r in result["results"]] == ["error", "error", "processed", "error", "duplicate"]
    assert 'subject:"Python application"' in queries[0]
    again = screening.screen_gmail(job["id"], 'subject:"Python application"')
    assert sum(r["status"] == "duplicate" for r in again["results"]) == 2


def test_nested_attachment_parsing():
    payload = {"parts": [{"mimeType": "multipart/mixed", "parts": [
        {"filename": "cv.PDF", "mimeType": "application/pdf", "body": {"attachmentId": "a1", "size": 50}}
    ]}]}
    found = gmail_reader.list_attachments(payload)
    assert len(found) == 1
    assert gmail_reader.is_supported(found[0])


def test_inline_attachment_data():
    import base64
    content = b"%PDF inline sample"
    payload = {"filename": "cv.pdf", "body": {"data": base64.urlsafe_b64encode(content).decode()}}
    found = gmail_reader.list_attachments(payload)
    assert gmail_reader.attachment_content(None, "m1", found[0]) == content


def test_completed_message_skipped_before_fetch_and_download(client, job, cv_bytes, monkeypatch):
    from src import database
    monkeypatch.setitem(sys.modules, "src.gmail_auth", SimpleNamespace(get_gmail_service=lambda: object()))
    monkeypatch.setattr(gmail_reader, "search_messages", lambda *a, **kw: ["m1"])
    calls = {"message": 0, "download": 0}
    def fetch(service, mid):
        calls["message"] += 1
        return mid
    def download(service, mid, aid):
        calls["download"] += 1
        return cv_bytes()
    monkeypatch.setattr(gmail_reader, "get_message", fetch)
    monkeypatch.setattr(gmail_reader, "parse_message", lambda mid: {
        "id": mid, "sender": "test@example.invalid", "subject": "Application", "attachments": [
            {"filename": "cv.docx", "attachment_id": "a1", "size": 100}]})
    monkeypatch.setattr(gmail_reader, "download_attachment", download)
    assert screening.screen_gmail(job["id"], "subject:Application")["results"][0]["status"] == "processed"
    assert database.completed_message(job["id"], "m1")
    assert screening.screen_gmail(job["id"], "subject:Application")["results"][0]["status"] == "duplicate"
    assert calls == {"message": 1, "download": 1}
    other = database.create_job("Other job", "Different requirements", job["requirements"])
    database.update_requirements(other["id"], job["requirements"])
    assert screening.screen_gmail(other["id"], "subject:Application")["results"][0]["status"] == "processed"
    assert calls == {"message": 2, "download": 2}


def test_failed_attachment_retries_while_successful_sibling_is_skipped(client, job, cv_bytes, monkeypatch):
    from src import database
    monkeypatch.setitem(sys.modules, "src.gmail_auth", SimpleNamespace(get_gmail_service=lambda: object()))
    monkeypatch.setattr(gmail_reader, "search_messages", lambda *a, **kw: ["m1"])
    monkeypatch.setattr(gmail_reader, "get_message", lambda *a: "m1")
    monkeypatch.setattr(gmail_reader, "parse_message", lambda mid: {
        "id": mid, "sender": "test@example.invalid", "subject": "Application", "attachments": [
            {"filename": "good.docx", "attachment_id": "good", "size": 100},
            {"filename": "retry.docx", "attachment_id": "retry", "size": 100}]})
    calls = []
    recovered = False
    content = cv_bytes()
    def download(service, mid, aid):
        calls.append(aid)
        return content if aid == "good" or recovered else b"invalid"
    monkeypatch.setattr(gmail_reader, "download_attachment", download)
    first = screening.screen_gmail(job["id"], "subject:Application")
    assert [r["status"] for r in first["results"]] == ["processed", "error"]
    assert not database.completed_message(job["id"], "m1")
    recovered = True
    second = screening.screen_gmail(job["id"], "subject:Application")
    assert [r["status"] for r in second["results"]] == ["duplicate", "duplicate"]
    assert calls == ["good", "retry", "retry"]
    assert database.completed_message(job["id"], "m1")
