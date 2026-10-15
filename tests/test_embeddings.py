import numpy as np
from src import embeddings


def test_cosine_passages_with_different_wording(monkeypatch):
    class Model:
        def encode(self, texts, normalize_embeddings):
            assert normalize_embeddings is True
            # A controlled normalized embedding for semantically equivalent wording.
            return np.array([[1., 0.] for _ in texts])
    monkeypatch.setattr(embeddings, "_model", lambda: Model())
    result = embeddings.semantic_evidence([{"id": "r1", "text": "SQL querying"}],
                                           "Retrieved records from relational databases.")
    assert result["r1"]["similarity"] == 1.0
    assert "relational databases" in result["r1"]["passage"]


def test_cached_model_is_loaded_without_hub_requests(monkeypatch):
    import sys
    from types import SimpleNamespace
    calls = []
    def model(name, **kwargs):
        calls.append(kwargs)
        return object()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=model))
    embeddings._model.cache_clear()
    try:
        embeddings._model()
        assert calls == [{"local_files_only": True}]
    finally:
        embeddings._model.cache_clear()


def test_first_use_downloads_when_no_local_model_exists(monkeypatch):
    import sys
    from types import SimpleNamespace
    calls = []
    def model(name, **kwargs):
        calls.append(kwargs)
        if kwargs.get("local_files_only"):
            raise OSError("No cache")
        return object()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=model))
    embeddings._model.cache_clear()
    try:
        embeddings._model()
        assert calls == [{"local_files_only": True}, {}]
    finally:
        embeddings._model.cache_clear()
