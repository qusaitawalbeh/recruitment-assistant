"""Evidence checks, explicit numeric guards and deterministic ranking."""
import re


def normalize(text):
    return " ".join(text.casefold().split())


def experience_duration(requirement, evidence):
    """Return only a single, scoped duration; ambiguous quotes require HR review."""
    durations = list(re.finditer(r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", evidence, re.I))
    if len(durations) != 1:
        return None
    duration = durations[0]
    # Ranges such as 2-5 years do not establish a single minimum duration.
    if re.search(r"\d\s*[-–]\s*$", evidence[:duration.start()]):
        return None
    sentence = next((part for part in re.split(r"(?<=[.!?])\s+|[;\n]", evidence)
                     if duration.group(0) in part), "")
    if re.search(r"\b(?:no|not|without|lack|lacking)\b", sentence, re.I):
        return None
    stop = set("at least minimum of a an the in with using use and or years year yrs yr experience experienced professional relevant work working programming required requires requirement strong good skills skill more than development developer hands on have has".split())
    scope = {word for word in re.findall(r"[\w+#]+", requirement.casefold())
             if word not in stop and not word.isdigit()}
    evidence_words = set(re.findall(r"[\w+#]+", sentence.casefold()))
    if scope and not scope.intersection(evidence_words):
        return None
    return float(duration.group(1))


def match_candidate(requirements, cv_text, assessments, semantic=None):
    assessments = {a["requirement_id"]: a for a in assessments}
    matches = []
    for req in requirements:
        assessment = assessments.get(req["id"], {})
        status = assessment.get("status", "no_evidence")
        evidence = assessment.get("evidence", "").strip()
        explanation = assessment.get("explanation", "")
        if not evidence or normalize(evidence) not in normalize(cv_text):
            status, evidence = "no_evidence", ""
            explanation = "No verifiable evidence found in the CV."
        if status == "no_evidence":
            evidence = ""
        minimum = req.get("minimum_years")
        if minimum is not None and status == "meets":
            years = experience_duration(req["text"], evidence)
            if years is None:
                status = "partially_meets"
                explanation = "The quoted duration is missing, ambiguous, or not tied to the required experience. HR verification is needed."
            elif years < minimum:
                status = "does_not_meet"
                explanation = f"Quoted experience is below the {minimum:g}-year minimum."
        matches.append({
            **req, "status": status, "evidence": evidence, "explanation": explanation,
            "semantic": (semantic or {}).get(req["id"]),
        })
    missing = [m["id"] for m in matches if m["must_have"] and m["status"] != "meets"]
    preferred = [m for m in matches if not m["must_have"]]
    points = {"meets": 1, "partially_meets": .5, "does_not_meet": 0, "no_evidence": 0}
    score = round(100 * sum(points[m["status"]] for m in preferred) / len(preferred), 2) if preferred else 0
    return {"matches": matches, "qualified": not missing, "missing_must_haves": missing,
            "score": score}


def rank_candidates(candidates, revision, top_n=20):
    qualified, review = [], []
    for candidate in candidates:
        candidate = dict(candidate)
        candidate["stale"] = candidate["job_revision"] != revision
        if candidate["qualified"] and not candidate["stale"]:
            qualified.append(candidate)
        else:
            review.append(candidate)
    qualified.sort(key=lambda c: (-c["score"], c["created_at"], c["id"]))
    for rank, candidate in enumerate(qualified, 1):
        candidate["rank"] = rank
    return {"qualified": qualified, "review": review, "top_candidates": qualified[:top_n],
            "statistics": {"total": len(candidates), "qualified": len(qualified),
                           "needs_review": len(review), "stale": sum(c["stale"] for c in review)}}
