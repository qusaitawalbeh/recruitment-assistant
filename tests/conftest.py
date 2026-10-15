from io import BytesIO
import pytest
from docx import Document
from fastapi.testclient import TestClient
from src import ai_extractor
from src.api import app


@pytest.fixture
def cv_bytes():
    def make(text="Alex Example. Python and SQL developer. 2 years of Python experience. "
                  "English speaker. Built reports and analytics tools."):
        doc = Document()
        doc.add_paragraph(text)
        stream = BytesIO()
        doc.save(stream)
        return stream.getvalue()
    return make


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_EMBEDDINGS", "false")
    monkeypatch.setattr(ai_extractor, "extract_job_requirements", lambda text: {
        "required_skills": ["Python"], "nice_to_have_skills": ["SQL"],
        "education": [], "languages": [], "certifications": [],
        "years_of_experience": None, "experience_notes": "",
    })
    monkeypatch.setattr(ai_extractor, "extract_cv_info", lambda text: {
        "candidate_name": text.split(".")[0], "skills": [s for s in ["Python", "SQL"] if s in text],
        "work_experience": [], "education": [], "languages": [], "certifications": [],
    })

    def assess(requirements, text, semantic=None):
        return [{"requirement_id": r["id"], "status": "meets" if r["text"] in text else "no_evidence",
                 "evidence": r["text"] if r["text"] in text else "",
                 "explanation": "Explicit mention."} for r in requirements]

    monkeypatch.setattr(ai_extractor, "assess_requirements", assess)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def job(client):
    response = client.post("/jobs", json={"title": "Data analyst", "description":
        "We need a Python developer with SQL skills to build analytical reports."})
    assert response.status_code == 201
    job = response.json()
    job["requirements"][0]["must_have"] = True
    response = client.put(f"/jobs/{job['id']}/requirements", json={"requirements": job["requirements"]})
    assert response.status_code == 200
    return response.json()
