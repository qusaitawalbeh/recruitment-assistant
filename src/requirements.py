"""Keep alternative qualifications together instead of scoring each alternative."""
import re


def education_from_source(description, extracted):
    if not extracted:
        return []
    sentences = re.split(r"(?<=[.!?])\s+|\n", description)
    education = [line.strip(" -\t•") for line in sentences if re.search(
        r"\b(?:bachelor|master|doctorate|phd|degree|diploma)\b", line, re.I)]
    if education and any(re.search(r"\bor\b", line, re.I) for line in education):
        return list(dict.fromkeys(education))
    return extracted


def repair_education(requirements, description):
    """Safely collapse a previously split, single alternative education criterion."""
    old = [r for r in requirements if r["category"] == "education"]
    source = education_from_source(description, [r["text"] for r in old])
    if len(old) < 2 or len(source) != 1 or not re.search(r"\bor\b", source[0], re.I):
        return requirements
    replacement = {**old[0], "text": source[0], "must_have": any(r["must_have"] for r in old)}
    result = []
    for req in requirements:
        if req["category"] != "education":
            result.append(req)
        elif req["id"] == old[0]["id"]:
            result.append(replacement)
    return result
