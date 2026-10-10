import json
import os
import re

import ollama
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")


JOB_PROMPT = """You are an information extraction system for a recruitment tool.
Read the job description below and extract the requirements.

Rules:
- Extract ONLY what is written in the text. Do not invent or assume anything.
- If the text does not mention a field, use an empty list [] (or null for years_of_experience).
- Return ONLY a valid JSON object. No explanations, no markdown.

Return JSON in exactly this format:
{{
  "job_title": "string",
  "required_skills": ["string"],
  "nice_to_have_skills": ["string"],
  "years_of_experience": number or null,
  "experience_notes": "string",
  "education": ["string"],
  "languages": ["string"],
  "certifications": ["string"]
}}

JOB DESCRIPTION:
\"\"\"
{text}
\"\"\"
"""


CV_PROMPT = """You are an information extraction system for a recruitment tool.
Read the CV text below and extract the candidate's information.

Rules:
- Extract ONLY what is explicitly written in the CV. Do not invent, guess, or assume anything.
- Do NOT add skills that the CV does not mention.
- If the CV does not mention a field, use an empty list [] (or null for numbers).
- The CV text may be messy or out of order. Do your best to read it.
- Return ONLY a valid JSON object. No explanations, no markdown.

Return JSON in exactly this format:
{{
  "candidate_name": "string",
  "skills": ["string"],
  "work_experience": [
    {{"title": "string", "company": "string", "duration": "string", "description": "string"}}
  ],
  "education": [
    {{"degree": "string", "institution": "string", "years": "string"}}
  ],
  "languages": ["string"],
  "certifications": ["string"]
}}

CV TEXT:
\"\"\"
{text}
\"\"\"
"""


def _clean_response(raw):

    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"```(?:json)?", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in the model response")
    return raw[start:end + 1]


def _ask_model(prompt):
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
        options={"temperature": 0},
    )
    return response["message"]["content"]


def _extract(prompt, retries=2):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            raw = _ask_model(prompt)
            return json.loads(_clean_response(raw))
        except Exception as e:
            last_error = e
            print(f"  Attempt {attempt} failed: {e}")
    raise RuntimeError(f"AI extraction failed: {last_error}")


def extract_job_requirements(job_text):
    return _extract(JOB_PROMPT.format(text=job_text))


def extract_cv_info(cv_text):
    return _extract(CV_PROMPT.format(text=cv_text))