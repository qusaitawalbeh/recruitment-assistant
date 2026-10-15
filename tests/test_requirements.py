from src.requirements import education_from_source, repair_education
from src.screening import requirements_from_extraction


DESCRIPTION = "Requirements:\n- Bachelor's degree in Computer Science, Data Science, Artificial Intelligence, or a related field.\n- Python programming."
SPLIT = ["Bachelor's degree in Computer Science", "Bachelor's degree in Data Science",
         "Bachelor's degree in Artificial Intelligence", "Bachelor's degree in a related field"]


def test_education_alternatives_count_as_one_requirement():
    result = requirements_from_extraction({"required_skills": ["Python"], "education": SPLIT}, DESCRIPTION)
    education = [r for r in result if r["category"] == "education"]
    assert len(education) == 1
    assert " or " in education[0]["text"]
    assert len(result) == 2


def test_independent_qualifications_are_not_combined():
    original = ["Bachelor's degree in Computer Science", "Master's degree preferred"]
    assert education_from_source("A bachelor's degree is required. A master's degree is preferred.", original) == original


def test_existing_repair_preserves_selected_must_have_and_id():
    original = [{"id": f"e{i}", "text": text, "category": "education", "must_have": i == 2,
                 "minimum_years": None} for i, text in enumerate(SPLIT)]
    result = repair_education(original, DESCRIPTION)
    assert len(result) == 1
    assert result[0]["id"] == "e0"
    assert result[0]["must_have"] is True
    assert repair_education(result, DESCRIPTION) == result


def test_education_alternative_is_evaluated_and_scored_once(client, cv_bytes, monkeypatch):
    from src import ai_extractor
    monkeypatch.setattr(ai_extractor, "extract_job_requirements", lambda _: {
        "required_skills": [], "education": SPLIT})
    job = client.post("/jobs", json={"title": "Analyst", "description": DESCRIPTION}).json()
    assert len(job["requirements"]) == 1
    criterion = job["requirements"][0]
    client.put(f"/jobs/{job['id']}/requirements", json={"requirements": [criterion]})
    monkeypatch.setattr(ai_extractor, "assess_requirements", lambda requirements, text, semantic: [{
        "requirement_id": criterion["id"], "status": "meets", "evidence": "Bachelor's degree in Data Science",
        "explanation": "One allowed alternative is present."}])
    response = client.post(f"/jobs/{job['id']}/screen/uploads", files={"files": ("cv.docx", cv_bytes(
        "Alex Example. Bachelor's degree in Data Science. Built analytics tools and reporting systems."))})
    assert response.json()["results"][0]["status"] == "processed"
    result = client.get(f"/jobs/{job['id']}/candidates").json()["qualified"][0]
    assert result["score"] == 100
    assert len(result["matches"]) == 1
