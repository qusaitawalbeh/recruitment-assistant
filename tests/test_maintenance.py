import json
import sqlite3
from pathlib import Path
from src import database, screening
from src.maintenance import repair_saved_education


def test_education_repair_backs_up_and_preserves_candidates_and_decisions(client, cv_bytes):
    criteria = [{"id": "e1", "text": "Bachelor's degree in Computer Science", "category": "education",
                 "must_have": False, "minimum_years": None},
                {"id": "e2", "text": "Bachelor's degree in Data Science", "category": "education",
                 "must_have": True, "minimum_years": None}]
    job = database.create_job("Analyst", "Bachelor's degree in Computer Science or Data Science.", criteria)
    job = database.update_requirements(job["id"], criteria)
    item = screening.ingest(job, "cv.docx", cv_bytes(), {"type": "upload"})
    cid = item["candidate_id"]
    database.update_decision(cid, "shortlist")
    report = repair_saved_education()
    assert report["changed_jobs"] == [job["id"]]
    repaired = database.get_job(job["id"])
    assert len(repaired["requirements"]) == 1
    assert repaired["requirements"][0]["must_have"] is True
    assert repaired["revision"] == job["revision"] + 1
    candidate = database.get_candidate(cid)
    assert candidate["decision"] == "shortlist"
    assert candidate["job_revision"] < repaired["revision"]
    assert Path(candidate["cv_path"]).exists()
    with sqlite3.connect(report["backup"]) as db:
        old = db.execute("SELECT requirements FROM jobs WHERE id=?", (job["id"],)).fetchone()[0]
        assert len(json.loads(old)) == 2
    assert repair_saved_education()["changed_jobs"] == []
