"""SQLite persistence. Legacy Week 1 JSON files remain untouched."""
import json
import os
import sqlite3
from contextlib import contextmanager
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def data_dir():
    path = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connection():
    with closing(sqlite3.connect(data_dir() / "recruitment.sqlite3", timeout=30)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                requirements TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0,
                revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                file_hash TEXT NOT NULL, filename TEXT NOT NULL, cv_path TEXT NOT NULL,
                cv_text TEXT NOT NULL, source TEXT NOT NULL, info TEXT NOT NULL,
                result TEXT NOT NULL, job_revision INTEGER NOT NULL,
                decision TEXT NOT NULL DEFAULT 'review_later', created_at TEXT NOT NULL,
                UNIQUE(job_id, file_hash)
            );
            CREATE TABLE IF NOT EXISTS gmail_messages (
                job_id TEXT NOT NULL REFERENCES jobs(id), message_id TEXT NOT NULL,
                completed_at TEXT NOT NULL, PRIMARY KEY(job_id,message_id)
            );
            CREATE TABLE IF NOT EXISTS gmail_attachments (
                job_id TEXT NOT NULL REFERENCES jobs(id), message_id TEXT NOT NULL,
                attachment_key TEXT NOT NULL, candidate_id TEXT NOT NULL REFERENCES candidates(id),
                filename TEXT NOT NULL, PRIMARY KEY(job_id,message_id,attachment_key)
            );
        """)
        yield db


def now():
    return datetime.now(timezone.utc).isoformat()


def _job(row):
    if row is None:
        raise KeyError("Job not found")
    job = dict(row)
    job["requirements"] = json.loads(job["requirements"])
    job["confirmed"] = bool(job["confirmed"])
    return job


def create_job(title, description, requirements):
    job_id = uuid4().hex
    with connection() as db:
        db.execute("INSERT INTO jobs(id,title,description,requirements,created_at) VALUES(?,?,?,?,?)",
                   (job_id, title, description, json.dumps(requirements), now()))
    return get_job(job_id)


def get_job(job_id):
    with connection() as db:
        return _job(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def list_jobs():
    with connection() as db:
        return [_job(row) for row in db.execute("SELECT * FROM jobs ORDER BY created_at DESC")]


def update_requirements(job_id, requirements):
    with connection() as db:
        cursor = db.execute("UPDATE jobs SET requirements=?,confirmed=1,revision=revision+1 WHERE id=?",
                            (json.dumps(requirements), job_id))
        if not cursor.rowcount:
            raise KeyError("Job not found")
    return get_job(job_id)


def _candidate(row):
    if row is None:
        raise KeyError("Candidate not found")
    candidate = dict(row)
    candidate["info"] = json.loads(candidate["info"])
    candidate["source"] = json.loads(candidate["source"])
    candidate.update(json.loads(candidate.pop("result")))
    return candidate


def get_candidate(candidate_id):
    with connection() as db:
        return _candidate(db.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone())


def find_duplicate(job_id, file_hash):
    with connection() as db:
        row = db.execute("SELECT * FROM candidates WHERE job_id=? AND file_hash=?",
                         (job_id, file_hash)).fetchone()
        return _candidate(row) if row else None


def list_candidates(job_id):
    with connection() as db:
        return [_candidate(row) for row in db.execute(
            "SELECT * FROM candidates WHERE job_id=? ORDER BY created_at,id", (job_id,))]


def save_candidate(job, file_hash, filename, cv_path, cv_text, source, info, result):
    candidate_id = uuid4().hex
    with connection() as db:
        cursor = db.execute("""INSERT OR IGNORE INTO candidates
            (id,job_id,file_hash,filename,cv_path,cv_text,source,info,result,job_revision,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (candidate_id, job["id"], file_hash, filename, str(cv_path), cv_text,
             json.dumps(source), json.dumps(info), json.dumps(result), job["revision"], now()))
        inserted = bool(cursor.rowcount)
        row = db.execute("SELECT * FROM candidates WHERE job_id=? AND file_hash=?",
                         (job["id"], file_hash)).fetchone()
        return _candidate(row), inserted


def update_result(candidate_id, revision, info, result):
    with connection() as db:
        db.execute("UPDATE candidates SET job_revision=?,info=?,result=? WHERE id=?",
                   (revision, json.dumps(info), json.dumps(result), candidate_id))
    return get_candidate(candidate_id)


def update_decision(candidate_id, decision):
    with connection() as db:
        cursor = db.execute("UPDATE candidates SET decision=? WHERE id=?", (decision, candidate_id))
        if not cursor.rowcount:
            raise KeyError("Candidate not found")
    return get_candidate(candidate_id)


def completed_message(job_id, message_id):
    with connection() as db:
        return db.execute("SELECT 1 FROM gmail_messages WHERE job_id=? AND message_id=?",
                          (job_id, message_id)).fetchone() is not None


def attachment_receipts(job_id, message_id):
    with connection() as db:
        return [dict(row) for row in db.execute(
            "SELECT attachment_key,candidate_id,filename FROM gmail_attachments WHERE job_id=? AND message_id=? ORDER BY attachment_key",
            (job_id, message_id))]


def record_attachment(job_id, message_id, attachment_key, candidate_id, filename):
    with connection() as db:
        db.execute("INSERT OR IGNORE INTO gmail_attachments VALUES(?,?,?,?,?)",
                   (job_id, message_id, attachment_key, candidate_id, filename))


def complete_message(job_id, message_id):
    with connection() as db:
        db.execute("INSERT OR IGNORE INTO gmail_messages VALUES(?,?,?)", (job_id, message_id, now()))
