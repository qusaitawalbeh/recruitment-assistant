"""Opt-in live acceptance against real Ollama/embeddings, optionally one known Gmail application.

Run: python -m scripts.acceptance [--gmail]
Temporary data is isolated; mailbox operations are read-only. No private document
content or account addresses are written to the acceptance report.
"""
import argparse
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from src import database
from src.api import app
from src.embeddings import semantic_evidence


def docx_bytes(text):
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


def pdf_bytes(text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    lines = []
    for line in text.splitlines():
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines.append(f"({escaped}) Tj 0 -18 Td")
    stream.set_data(("BT /F1 10 Tf 40 740 Td " + " ".join(lines) + " ET").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def known_gmail_message():
    # Read only enough to select one previously collected application.
    for job in database.list_jobs():
        for candidate in database.list_candidates(job["id"]):
            if candidate["source"].get("type") == "gmail":
                return candidate["source"]["email_id"]
    raise RuntimeError("--gmail requires a previously collected Gmail application in the local database")


@contextmanager
def isolated_data():
    old_data, old_embeddings = os.environ.get("DATA_DIR"), os.environ.get("ENABLE_EMBEDDINGS")
    try:
        with TemporaryDirectory(prefix="recruitment-acceptance-") as folder:
            os.environ["DATA_DIR"] = folder
            os.environ["ENABLE_EMBEDDINGS"] = "true"
            yield
    finally:
        for key, value in [("DATA_DIR", old_data), ("ENABLE_EMBEDDINGS", old_embeddings)]:
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run(include_gmail=False):
    message_id = known_gmail_message() if include_gmail else None
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "checks": []}
    def passed(name):
        report["checks"].append({"name": name, "status": "passed"})
        print(f"PASS: {name}", flush=True)
    with isolated_data(), TestClient(app) as client:
        description = (
            "Python Analyst. Required skills: Python programming.\n"
            "At least 2 years of Python experience.\n"
            "Bachelor's degree in Computer Science or Data Science.\n"
            "Preferred skill: SQL querying."
        )
        response = client.post("/jobs", json={"title": "Python Analyst", "description": description})
        assert response.status_code == 201, response.text
        job = response.json()
        assert len([r for r in job["requirements"] if r["category"] == "education"]) == 1
        # HR reviews extraction and explicitly confirms the acceptance criteria.
        criteria = [
            {"id": "python", "text": "Python programming", "category": "skill", "must_have": True},
            {"id": "experience", "text": "At least 2 years of Python experience", "category": "experience", "must_have": True, "minimum_years": 2},
            {"id": "degree", "text": "Bachelor's degree in Computer Science or Data Science", "category": "education", "must_have": True},
            {"id": "sql", "text": "SQL querying", "category": "skill", "must_have": False},
        ]
        assert client.put(f"/jobs/{job['id']}/requirements", json={"requirements": criteria}).status_code == 200
        passed("real_job_extraction_and_hr_confirmation")
        full = (
            "Qualified Example\nSkills: Python programming and SQL querying.\n"
            "Experience: 3 years of Python experience building reporting applications.\n"
            "Education: Bachelor's degree in Data Science."
        )
        missing = (
            "Missing Skill Example\nSkills: Excel and Java.\n"
            "Experience: 3 years of Java experience building reports.\n"
            "Education: Bachelor's degree in Data Science."
        )
        mixed = (
            "Mixed Duration Example\nSkills: Python programming and SQL querying.\n"
            "Experience: 5 years of Java experience and 1 year of Python experience.\n"
            "Education: Bachelor's degree in Computer Science."
        )
        good = docx_bytes(full)
        upload = client.post(f"/jobs/{job['id']}/screen/uploads", files=[
            ("files", ("qualified.docx", good)), ("files", ("missing.pdf", pdf_bytes(missing))),
            ("files", ("mixed.docx", docx_bytes(mixed))), ("files", ("corrupt.pdf", b"%PDF invalid")),
        ])
        assert upload.status_code == 200, upload.text
        rows = upload.json()["results"]
        assert [r["status"] for r in rows] == ["processed", "processed", "processed", "error"], rows
        passed("real_pdf_docx_batch_and_independent_file_error")
        candidates = [client.get(f"/candidates/{r['candidate_id']}").json() for r in rows[:3]]
        assert candidates[0]["qualified"], "Explicitly qualified synthetic CV was not qualified"
        assert not candidates[1]["qualified"], "Missing mandatory skill incorrectly passed"
        assert not candidates[2]["qualified"], "Unrelated years incorrectly passed"
        assert all(c["semantic_enabled"] for c in candidates)
        passed("real_model_must_haves_alternative_degree_and_scoped_experience")
        ranking = client.get(f"/jobs/{job['id']}/candidates?top_n=1").json()
        assert len(ranking["top_candidates"]) == 1
        assert len(ranking["review"]) == 2
        cid = candidates[0]["id"]
        assert client.get(f"/candidates/{cid}/cv").content == good
        assert client.patch(f"/candidates/{cid}/decision", json={"decision": "shortlist"}).status_code == 200
        assert client.get(f"/candidates/{cid}").json()["decision"] == "shortlist"
        duplicate = client.post(f"/jobs/{job['id']}/screen/uploads", files={"files": ("renamed.docx", good)}).json()
        assert duplicate["results"][0]["status"] == "duplicate"
        passed("ranking_original_cv_decision_persistence_and_duplicate")
        other = client.post("/jobs", json={"title": "SQL Analyst", "description":
            "SQL Analyst. Required skill: SQL querying. Preferred skill: Excel reporting."})
        assert other.status_code == 201, other.text
        other_id = other.json()["id"]
        client.put(f"/jobs/{other_id}/requirements", json={"requirements": [
            {"id": "sql", "text": "SQL querying", "category": "skill", "must_have": True}]})
        second = client.post(f"/jobs/{other_id}/screen/uploads", files={"files": ("cv.docx", good)}).json()
        assert second["results"][0]["status"] == "processed"
        passed("second_job_and_per_job_application_identity")
        related = semantic_evidence([{"id": "sql", "text": "SQL querying"}], "Retrieved records from relational databases.")["sql"]["similarity"]
        unrelated = semantic_evidence([{"id": "sql", "text": "SQL querying"}], "Painted watercolor landscapes for an art exhibition.")["sql"]["similarity"]
        assert related > unrelated, (related, unrelated)
        report["semantic_check"] = {"related_similarity": related, "unrelated_similarity": unrelated}
        passed("real_embedding_different_wording_orders_related_above_unrelated")
        if message_id:
            from src.gmail_auth import get_gmail_service
            from src.gmail_reader import get_message, get_header
            message = get_message(get_gmail_service(), message_id)
            header = get_header(message, "Message-ID")
            assert header, "Known application has no RFC Message-ID for a narrow search"
            payload = {"query": f"rfc822msgid:{header}", "max_results": 1}
            collected = client.post(f"/jobs/{job['id']}/screen/gmail", json=payload)
            assert collected.status_code == 200, collected.text
            result = collected.json()
            assert result["emails_found"] == 1 and result["results"], "Known Gmail application was not found"
            assert all(r["status"] != "error" for r in result["results"]), "Live Gmail attachment processing failed"
            repeated = client.post(f"/jobs/{job['id']}/screen/gmail", json=payload).json()
            assert all(r["status"] == "duplicate" for r in repeated["results"])
            passed("real_readonly_gmail_collection_model_screening_and_repeat_skip")
        # Exercise the actual Streamlit result page against the real processed data.
        import requests
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest
        def transport(method, url, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("stream", None)
            response = client.request(method, url.split(":8000", 1)[1], **kwargs)
            adapted = requests.Response()
            adapted.status_code, adapted._content = response.status_code, response.content
            adapted.headers.update(response.headers)
            return adapted
        def page():
            from app import results_page
            results_page()
        # Only the HTTP transport is bridged to TestClient; no model/mail outputs are mocked.
        with patch.object(requests, "request", transport):
            ui = AppTest.from_function(page, default_timeout=60).run()
            assert not ui.exception
        passed("streamlit_results_page_with_live_processed_data")
    report["status"] = "passed"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gmail", action="store_true", help="Read and screen one previously collected Gmail application in isolation")
    parser.add_argument("--report", default="tmp/live-acceptance.json")
    args = parser.parse_args()
    report = run(args.gmail)
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Live acceptance passed; report: {path}")


if __name__ == "__main__":
    main()
