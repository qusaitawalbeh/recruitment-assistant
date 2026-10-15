import json
import pytest
from pypdf import PdfWriter
from src import ai_extractor
from src.models import JobExtraction
from src.cv_extractor import extract_cv_text, CVExtractionError


def valid_job(**overrides):
    return {"job_title": "", "required_skills": [], "nice_to_have_skills": [],
            "years_of_experience": None, "experience_notes": "", "education": [],
            "languages": [], "certifications": [], **overrides}


def test_docx_extraction(tmp_path, cv_bytes):
    path = tmp_path / "cv.docx"
    path.write_bytes(cv_bytes())
    assert "Python" in extract_cv_text(path)


def test_pdf_text_extraction(tmp_path):
    # A small valid PDF with one text stream: no fixture depends on private CVs.
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 40 700 Td (Alex Example has Python and SQL experience building analytics tools.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    path = tmp_path / "cv.pdf"
    writer.write(path)
    assert "Python and SQL" in extract_cv_text(path)


def test_blank_corrupt_encrypted_and_unsupported(tmp_path):
    blank = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    writer.write(blank)
    with pytest.raises(CVExtractionError, match="No readable text"):
        extract_cv_text(blank)
    encrypted = tmp_path / "encrypted.pdf"
    writer.encrypt("password")
    writer.write(encrypted)
    with pytest.raises(CVExtractionError, match="password protected"):
        extract_cv_text(encrypted)
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"PK invalid")
    with pytest.raises(CVExtractionError, match="Could not read file"):
        extract_cv_text(broken)
    with pytest.raises(CVExtractionError, match="Unsupported"):
        extract_cv_text(tmp_path / "cv.txt")


def test_schema_retry_on_invalid_llm_output(monkeypatch):
    responses = iter(['{"required_skills": "Python"}', '<think>reasoning</think>```json\n' + json.dumps(valid_job(required_skills=["Python"])) + '\n```'])
    monkeypatch.setattr(ai_extractor, "_ask_model", lambda *args: next(responses))
    result = ai_extractor._extract("prompt", JobExtraction)
    assert result.required_skills == ["Python"]


def test_schema_exhausted_retry(monkeypatch):
    monkeypatch.setattr(ai_extractor, "_ask_model", lambda *args: '{"years_of_experience": -4}')
    with pytest.raises(RuntimeError, match="Ollama extraction failed"):
        ai_extractor._extract("prompt", JobExtraction)


def test_incomplete_assessment_rejected(monkeypatch):
    monkeypatch.setattr(ai_extractor, "_ask_model", lambda *args: '{"assessments": []}')
    with pytest.raises(RuntimeError, match="missing or duplicate"):
        ai_extractor.assess_requirements([{"id": "r1", "text": "Python"}], "CV")


def test_explicit_minimum_recovered_from_source(monkeypatch):
    monkeypatch.setattr(ai_extractor, "_ask_model", lambda *args: json.dumps(valid_job(required_skills=["Python"])))
    result = ai_extractor.extract_job_requirements("At least 2 years of experience using Python.")
    assert result["years_of_experience"] == 2
    assert "Python" in result["experience_notes"]


def test_oversized_prompt_rejected_before_ollama(monkeypatch):
    monkeypatch.setenv("OLLAMA_CONTEXT", "8192")
    with pytest.raises(ValueError, match="exceed the configured model context"):
        ai_extractor._ask_model("x" * 10000, JobExtraction)


def test_assessments_are_batched_with_only_relevant_semantic_hints(monkeypatch):
    from src.models import AssessmentBatch
    calls = []
    def extract(prompt, schema):
        import re
        reqs = json.loads(re.search(r"<requirements>(.*?)</requirements>", prompt, re.S).group(1))
        hints = json.loads(re.search(r"<semantic_suggestions>(.*?)</semantic_suggestions>", prompt, re.S).group(1))
        assert set(hints) == {r["id"] for r in reqs}
        calls.append(len(reqs))
        return AssessmentBatch(assessments=[{"requirement_id": r["id"], "status": "no_evidence"} for r in reqs])
    monkeypatch.setattr(ai_extractor, "_extract", extract)
    reqs = [{"id": f"r{i}", "text": "Skill"} for i in range(10)]
    result = ai_extractor.assess_requirements(reqs, "Synthetic CV", {r["id"]: {} for r in reqs})
    assert calls == [4, 4, 2]
    assert [a["requirement_id"] for a in result] == [r["id"] for r in reqs]
