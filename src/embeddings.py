"""Lazy-load the embedding model only when semantic matching is enabled."""
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    # Reuse a complete local model without waiting for Hub metadata on every launch.
    try:
        return SentenceTransformer(model, local_files_only=True)
    except (OSError, ValueError):
        return SentenceTransformer(model)


def semantic_evidence(requirements, cv_text):
    words = cv_text.split()
    chunks = [" ".join(words[i:i + 100]) for i in range(0, len(words), 70)]
    if not chunks:
        return {}
    model = _model()
    queries = model.encode([r["text"] for r in requirements], normalize_embeddings=True)
    passages = model.encode(chunks, normalize_embeddings=True)
    similarities = queries @ passages.T
    return {
        r["id"]: {"similarity": round(float(row.max()), 4),
                  "passage": chunks[int(row.argmax())]}
        for r, row in zip(requirements, similarities)
    }
