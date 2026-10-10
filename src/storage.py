import json
import os

CANDIDATES_PATH = "data/candidates.json"


def load_candidates():
    if os.path.exists(CANDIDATES_PATH):
        with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_candidates(candidates):
    os.makedirs(os.path.dirname(CANDIDATES_PATH), exist_ok=True)
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)