"""Reusable processing workflow for API, local uploads and Gmail."""
import hashlib
import os
from pathlib import Path
from . import ai_extractor, database
from .cv_extractor import extract_cv_text, CVExtractionError
from .embeddings import semantic_evidence
from .matcher import match_candidate
from .models import Requirement, RequirementsUpdate
from .requirements import education_from_source

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_CV_CHARS = 60000


def requirements_from_extraction(extracted, description=""):
    extracted = {**extracted, "education": education_from_source(description, extracted.get("education", []))}
    requirements = []
    specific = {text.strip().casefold() for field in ("education", "languages", "certifications")
                for text in extracted.get(field, [])}
    for field, category in [("required_skills", "skill"), ("nice_to_have_skills", "skill"),
                            ("education", "education"), ("languages", "language"),
                            ("certifications", "certification")]:
        for text in extracted.get(field, []):
            if category == "skill" and text.strip().casefold() in specific:
                continue
            if text.strip() and not any(r["text"].casefold() == text.strip().casefold() for r in requirements):
                requirements.append(Requirement(id=f"r{len(requirements)+1}", text=text,
                                                category=category).model_dump())
    years = extracted.get("years_of_experience")
    notes = extracted.get("experience_notes", "")
    if notes or years is not None:
        requirements.append(Requirement(
            id=f"r{len(requirements)+1}", text=notes or f"At least {years:g} years of experience",
            category="experience", minimum_years=years).model_dump())
    return RequirementsUpdate(requirements=requirements).model_dump()["requirements"]


def ready_job(job_id):
    job = database.get_job(job_id)
    if not job["confirmed"]:
        raise ValueError("Review the requirements and confirm your Must-Have selections first")
    return job


def evaluate(job, text):
    if len(text) > MAX_CV_CHARS:
        raise CVExtractionError(f"CV exceeds the {MAX_CV_CHARS:,}-character processing limit")
    info = ai_extractor.extract_cv_info(text)
    semantic = {}
    if os.getenv("ENABLE_EMBEDDINGS", "true").lower() == "true":
        semantic = semantic_evidence(job["requirements"], text)
    assessments = ai_extractor.assess_requirements(job["requirements"], text, semantic)
    result = match_candidate(job["requirements"], text, assessments, semantic)
    result["semantic_enabled"] = bool(semantic)
    return info, result


def ingest(job, filename, content, source):
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise CVExtractionError("Only PDF and DOCX files are supported")
    if not content or len(content) > MAX_FILE_BYTES:
        raise CVExtractionError("CV must be non-empty and at most 10 MB")
    if not content.startswith(b"%PDF" if suffix == ".pdf" else b"PK"):
        raise CVExtractionError("File content does not match its extension")
    digest = hashlib.sha256(content).hexdigest()
    existing = database.find_duplicate(job["id"], digest)
    if existing:
        return {"status": "duplicate", "candidate_id": existing["id"], "filename": filename}
    folder = database.data_dir() / "cvs" / job["id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}{suffix}"
    path.write_bytes(content)
    text = extract_cv_text(path)
    info, result = evaluate(job, text)
    candidate, inserted = database.save_candidate(job, digest, Path(filename).name, path,
                                                  text, source, info, result)
    return {"status": "processed" if inserted else "duplicate",
            "candidate_id": candidate["id"], "filename": filename}


def rescreen(job_id):
    job = ready_job(job_id)
    results = []
    for candidate in database.list_candidates(job_id):
        try:
            info, result = evaluate(job, candidate["cv_text"])
            database.update_result(candidate["id"], job["revision"], info, result)
            results.append({"candidate_id": candidate["id"], "status": "processed"})
        except Exception as exc:
            results.append({"candidate_id": candidate["id"], "status": "error", "error": str(exc)})
    return results


def screen_gmail(job_id, query, max_results=50):
    from .gmail_auth import get_gmail_service
    from .gmail_reader import (search_messages, get_message, parse_message, is_supported,
                               attachment_content)
    job = ready_job(job_id)
    service = get_gmail_service()
    ids = search_messages(service, query=f"({query}) has:attachment (filename:pdf OR filename:docx)",
                          max_results=max_results)
    results = []
    for message_id in ids:
        try:
            receipts = database.attachment_receipts(job_id, message_id)
            if database.completed_message(job_id, message_id):
                results.extend({"status": "duplicate", "email_id": message_id,
                                "candidate_id": r["candidate_id"], "filename": r["filename"]} for r in receipts)
                continue
            email = parse_message(get_message(service, message_id))
            supported = [a for a in email["attachments"] if is_supported(a)]
            successful = {r["attachment_key"]: r for r in receipts}
            failed = False
            for attachment in supported:
                key = attachment.get("attachment_id") or hashlib.sha256(
                    (attachment["filename"] + "\0" + attachment.get("inline_data", "")).encode()).hexdigest()
                if key in successful:
                    receipt = successful[key]
                    results.append({"status": "duplicate", "email_id": message_id,
                                    "filename": receipt["filename"], "candidate_id": receipt["candidate_id"]})
                    continue
                try:
                    if attachment.get("size", 0) > MAX_FILE_BYTES:
                        raise CVExtractionError("Attachment exceeds the 10 MB limit")
                    content = attachment_content(service, message_id, attachment)
                    result = ingest(job, attachment["filename"], content,
                                    {"type": "gmail", "email_id": message_id,
                                     "sender": email["sender"], "subject": email["subject"]})
                    database.record_attachment(job_id, message_id, key, result["candidate_id"], attachment["filename"])
                    results.append(result)
                except Exception as exc:
                    failed = True
                    results.append({"status": "error", "email_id": message_id,
                                    "filename": attachment["filename"], "error": str(exc)})
            if not failed:
                database.complete_message(job_id, message_id)
        except Exception as exc:
            results.append({"status": "error", "email_id": message_id, "error": str(exc)})
    return {"emails_found": len(ids), "results": results}
