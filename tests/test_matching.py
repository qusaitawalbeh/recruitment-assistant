import pytest
from src.matcher import match_candidate, rank_candidates


def requirement(must_have=True, **kwargs):
    return {"id": "r1", "text": "Python", "category": "skill", "must_have": must_have,
            "minimum_years": None, **kwargs}


def assessment(evidence, status="meets"):
    return {"requirement_id": "r1", "status": status, "evidence": evidence, "explanation": "Model explanation"}


@pytest.mark.parametrize("evidence", ["", "Invented Python quotation"])
def test_fabricated_evidence_cannot_qualify(evidence):
    result = match_candidate([requirement()], "CV mentions SQL only", [assessment(evidence)])
    assert result["qualified"] is False
    assert result["matches"][0]["status"] == "no_evidence"


def test_whitespace_normalized_quotation_and_partial_scoring():
    result = match_candidate([requirement(False)], "Used Python\n for analytics", [assessment("Python for analytics", "partially_meets")])
    assert result["score"] == 50
    assert result["qualified"] is True


@pytest.mark.parametrize("quote,expected", [("2 years of Python", "does_not_meet"),
                                            ("Experienced in Python", "partially_meets"),
                                            ("4 years of Python", "meets")])
def test_explicit_years_guard(quote, expected):
    req = requirement(category="experience", minimum_years=3)
    result = match_candidate([req], quote, [assessment(quote)])
    assert result["matches"][0]["status"] == expected
    assert result["qualified"] == (expected == "meets")


def test_semantic_similarity_does_not_pass_mandatory_requirement():
    result = match_candidate([requirement()], "SQL only", [assessment("", "no_evidence")],
                             {"r1": {"similarity": .99, "passage": "SQL only"}})
    assert not result["qualified"]


def test_partial_must_have_not_qualified():
    result = match_candidate([requirement()], "Python basics", [assessment("Python basics", "partially_meets")])
    assert not result["qualified"]


def test_stable_ties_and_stale_exclusion():
    base = {"qualified": True, "score": 50, "created_at": "2026-01-01", "job_revision": 1}
    result = rank_candidates([{**base, "id": "b"}, {**base, "id": "a"},
                              {**base, "id": "stale", "job_revision": 0}], 1, 1)
    assert [c["id"] for c in result["qualified"]] == ["a", "b"]
    assert result["review"][0]["id"] == "stale"
    assert len(result["top_candidates"]) == 1


@pytest.mark.parametrize("quote", [
    "5 years of Java experience and 1 year of Python experience.",
    "5 years of Java experience. Also developed Python projects.",
    "5 years of Java experience.",
    "2-5 years of Python experience.",
    "No Python experience; 5 years of Java experience.",
])
def test_unrelated_or_ambiguous_duration_cannot_pass_must_have(quote):
    req = requirement(text="At least 3 years of Python experience", category="experience", minimum_years=3)
    result = match_candidate([req], quote, [assessment(quote)])
    assert result["matches"][0]["status"] == "partially_meets"
    assert result["qualified"] is False


def test_short_scoped_duration_quote_can_pass_even_when_cv_mentions_other_durations():
    req = requirement(text="At least 3 years of Python experience", category="experience", minimum_years=3)
    cv = "5 years of Java experience. 4 years of Python experience."
    result = match_candidate([req], cv, [assessment("4 years of Python experience.")])
    assert result["qualified"] is True
