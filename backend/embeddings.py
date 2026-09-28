"""Embeddings: all-MiniLM-L6-v2 via sentence-transformers, with a TF-IDF
fallback if the model cannot be loaded."""
from __future__ import annotations

import numpy as np

_model = None
_tried = False


def _get_model():
    global _model, _tried
    if _tried:
        return _model
    _tried = True
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception as e:
        print(f"[embeddings] MiniLM unavailable ({e}); using TF-IDF fallback")
        _model = None
    return _model


def embed(texts: list[str]) -> np.ndarray:
    m = _get_model()
    if m is not None:
        return np.asarray(m.encode(texts, show_progress_bar=False))
    from sklearn.feature_extraction.text import TfidfVectorizer
    return TfidfVectorizer(max_features=512, stop_words="english") \
        .fit_transform(texts).toarray()


def dim() -> int:
    return 384 if _get_model() is not None else 512
