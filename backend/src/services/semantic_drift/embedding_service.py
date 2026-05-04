"""
Semantic similarity between baseline text and newly detected column meaning.

- Primary: pre-trained SentenceTransformer `all-MiniLM-L6-v2` (no fine-tuning).
- Fallback: scikit-learn TF-IDF + cosine if sentence-transformers unavailable.

Viva: embeddings only compare meaning strings; governance rules set the final decision.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

_sim_model = None
_tfidf_vec = None
_use_st: Optional[bool] = None


def _load_st():
    global _sim_model, _use_st
    if _use_st is not None:
        return _sim_model
    try:
        from sentence_transformers import SentenceTransformer

        _sim_model = SentenceTransformer("all-MiniLM-L6-v2")
        _use_st = True
    except Exception:
        _sim_model = None
        _use_st = False
    return _sim_model


def build_comparison_text(profile: Dict[str, Any]) -> str:
    parts = [
        str(profile.get("column_name", "")),
        str(profile.get("business_meaning") or profile.get("detected_business_meaning", "")),
        str(profile.get("role", "")),
        str(profile.get("domain", "")),
        str(profile.get("unit", "")),
        str(profile.get("scale", "")),
        str(profile.get("value_direction", "")),
    ]
    return " | ".join(p for p in parts if p)


def calculate_semantic_similarity(text1: str, text2: str) -> float:
    """Return cosine similarity in [0, 1] (clamped)."""
    t1, t2 = (text1 or "").strip(), (text2 or "").strip()
    if not t1 or not t2:
        return 0.0

    # Pytest / CI: avoid downloading sentence-transformers models (use TF-IDF only).
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("SEMANTIC_DRIFT_FORCE_TFIDF") == "1":
        return _similarity_tfidf_pair(t1, t2)

    model = _load_st()
    if _use_st and model is not None:
        emb = model.encode([t1, t2], normalize_embeddings=True)
        a, b = emb[0], emb[1]
        sim = float(a @ b)
        return max(0.0, min(1.0, sim))

    return _similarity_tfidf_pair(t1, t2)


def _similarity_tfidf_pair(t1: str, t2: str) -> float:
    """TF-IDF cosine on two strings (pairwise demo / test path)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vec = TfidfVectorizer(max_features=256)
    try:
        m = vec.fit_transform([t1, t2])
        sim = float(cosine_similarity(m[0], m[1])[0][0])
        return max(0.0, min(1.0, sim))
    except Exception:
        return 0.5 if t1.lower() == t2.lower() else 0.35
