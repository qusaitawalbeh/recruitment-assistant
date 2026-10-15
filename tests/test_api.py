from src import ai_extractor, database


def upload(client, job, content, filename="cv.docx"):
    response = client.post(f"/jobs/{job['id']}/screen/uploads", files=[("files", (filename, content))])
    assert response.status_code == 200
    return response.json()["results"][0]


def test_full_workflow_decisions_and_original(client, job, cv_bytes):
    content = cv_bytes()
    processed = upload(client, job, content)
    assert processed["status"] == "processed"
    cid = processed["candidate_id"]
    result = client.get(f"/jobs/{job['id']}/candidates?top_n=1").json()
    assert result["statistics"] == {"total": 1, "qualified": 1, "needs_review": 0, "stale": 0}
    assert result["top_candidates"][0]["score"] == 100
    assert result["top_candidates"][0]["rank"] == 1
    assert "cv_path" not in result["top_candidates"][0]
    assert client.get(f"/candidates/{cid}/cv").content == content
    assert client.patch(f"/candidates/{cid}/decision", json={"decision": "shortlist"}).json()["decision"] == "shortlist"
    assert database.get_candidate(cid)["decision"] == "shortlist"
    assert client.get(f"/candidates/{cid}").json()["info"]["candidate_name"] == "Alex Example"


def test_hash_duplicates_across_names_and_sources_per_job(client, job, cv_bytes):
    content = cv_bytes()
    first = upload(client, job, content, "one.docx")
    again = upload(client, job, content, "renamed.docx")
    assert again["status"] == "duplicate"
    assert first["candidate_id"] == again["candidate_id"]
    other = database.create_job("Other", "Another role", job["requirements"])
    database.update_requirements(other["id"], job["requirements"])
    assert upload(client, other, content)["status"] == "processed"


def test_invalid_file_does_not_stop_batch(client, job, cv_bytes):
    response = client.post(f"/jobs/{job['id']}/screen/uploads", files=[
        ("files", ("broken.pdf", b"%PDF invalid data")),
        ("files", ("wrong.docx", b"not a zip")),
        ("files", ("good.docx", cv_bytes())),
    ])
    assert [r["status"] for r in response.json()["results"]] == ["error", "error", "processed"]


def test_unqualified_remains_for_hr_and_rank_is_preferred(client, job, cv_bytes):
    upload(client, job, cv_bytes("Weak Candidate. SQL reports and dashboard development. " * 3))
    upload(client, job, cv_bytes("Basic Candidate. Python development and application support. " * 3))
    upload(client, job, cv_bytes())
    results = client.get(f"/jobs/{job['id']}/candidates?top_n=1").json()
    assert results["statistics"]["total"] == 3
    assert len(results["qualified"]) == 2
    assert [c["score"] for c in results["qualified"]] == [100, 0]
    assert len(results["top_candidates"]) == 1
    assert results["review"][0]["missing_must_haves"] == ["r1"]
    cid = results["review"][0]["id"]
    assert client.patch(f"/candidates/{cid}/decision", json={"decision": "shortlist"}).status_code == 200


def test_criteria_change_invalidates_and_rescreen_preserves_decision(client, job, cv_bytes):
    cid = upload(client, job, cv_bytes())["candidate_id"]
    client.patch(f"/candidates/{cid}/decision", json={"decision": "reject"})
    criteria = job["requirements"]
    criteria[1]["text"] = "Rust"
    criteria[1]["must_have"] = True
    client.put(f"/jobs/{job['id']}/requirements", json={"requirements": criteria})
    results = client.get(f"/jobs/{job['id']}/candidates").json()
    assert not results["qualified"]
    assert results["review"][0]["stale"] is True
    assert client.post(f"/jobs/{job['id']}/rescreen").json()["results"][0]["status"] == "processed"
    result = client.get(f"/candidates/{cid}").json()
    assert result["stale"] is False
    assert result["qualified"] is False
    assert result["decision"] == "reject"


def test_validation_and_missing_records(client, job, cv_bytes):
    assert client.post("/jobs", json={"title": " ", "description": "x"}).status_code == 422
    assert client.get("/jobs/missing").status_code == 404
    assert client.get("/candidates/missing").status_code == 404
    assert client.get("/candidates/missing/cv").status_code == 404
    assert client.get(f"/jobs/{job['id']}/candidates?top_n=0").status_code == 422
    criteria = job["requirements"]
    assert client.put(f"/jobs/{job['id']}/requirements", json={"requirements": []}).status_code == 422
    assert client.put(f"/jobs/{job['id']}/requirements", json={"requirements": [criteria[0], criteria[0]]}).status_code == 422
    cid = upload(client, job, cv_bytes())["candidate_id"]
    assert client.patch(f"/candidates/{cid}/decision", json={"decision": "hire"}).status_code == 422
    assert client.post(f"/jobs/{job['id']}/screen/gmail", json={"query": " "}).status_code == 422


def test_confirmation_required(client, cv_bytes):
    job = client.post("/jobs", json={"title": "Analyst", "description": "A Python and SQL analyst job description."}).json()
    assert client.post(f"/jobs/{job['id']}/screen/uploads", files={"files": ("cv.docx", cv_bytes())}).status_code == 422


def test_model_failure_retryable_without_duplicate_record(client, job, cv_bytes, monkeypatch):
    original = ai_extractor.extract_cv_info
    def fail(text):
        raise RuntimeError("Ollama unavailable")
    monkeypatch.setattr(ai_extractor, "extract_cv_info", fail)
    assert upload(client, job, cv_bytes())["status"] == "error"
    assert database.list_candidates(job["id"]) == []
    monkeypatch.setattr(ai_extractor, "extract_cv_info", original)
    assert upload(client, job, cv_bytes())["status"] == "processed"


def test_job_extraction_dependency_error(client, monkeypatch):
    def fail(text):
        raise RuntimeError("Ollama unavailable")
    monkeypatch.setattr(ai_extractor, "extract_job_requirements", fail)
    response = client.post("/jobs", json={"title": "Developer", "description": "A Python and SQL development role for an analyst."})
    assert response.status_code == 503


def test_missing_original_and_path_boundary(client, job, cv_bytes):
    from pathlib import Path
    cid = upload(client, job, cv_bytes())["candidate_id"]
    Path(database.get_candidate(cid)["cv_path"]).unlink()
    assert client.get(f"/candidates/{cid}/cv").status_code == 404
    with database.connection() as db:
        db.execute("UPDATE candidates SET cv_path=? WHERE id=?", (__file__, cid))
    assert client.get(f"/candidates/{cid}/cv").status_code == 404
