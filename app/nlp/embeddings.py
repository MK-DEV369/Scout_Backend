from functools import lru_cache
from typing import Any, List, Optional

import hashlib
import logging
import re

import torch

from app.core.config import settings


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embedding_model() -> Optional[Any]:
    """Load and cache the SentenceTransformer model.

    Uses `settings.embedding_model` if present; defaults to all-mpnet-base-v2.
    """
    model_id = getattr(settings, "embedding_model", "sentence-transformers/all-mpnet-base-v2")
    device = "cuda" if torch.cuda.is_available() else "cpu"

    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_id, device=device)
    except Exception as exc:
        logger.warning(
            "SentenceTransformer unavailable; using fallback embeddings for %s (%s)",
            model_id,
            exc,
        )
        return None


def _fallback_embedding(text: str, dimensions: int = 384) -> List[float]:
    tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    if not tokens:
        return []

    vector = [0.0] * dimensions
    for token in tokens[:512]:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0

    norm = sum(value * value for value in vector) ** 0.5
    if norm:
        vector = [value / norm for value in vector]
    return vector


def embed_text(text: str) -> List[float]:
    """Return a single embedding vector for the provided text as a list of floats."""
    if not text:
        return []

    model = get_embedding_model()
    if model is None:
        return _fallback_embedding(text)

    # keep a sane max length (characters) to avoid very long inputs
    snippet = text[:2000]
    emb = model.encode(snippet, convert_to_numpy=True)
    try:
        return emb.tolist()
    except Exception:
        return [float(x) for x in emb]
