"""Embedding layer for recall memory vectors.

Supports two backends:
  - Local: sentence-transformers/all-MiniLM-L6-v2 (default, no API key needed)
  - OpenAI: text-embedding-3-small (when OPENAI_API_KEY set and RECALL_EMBEDDINGS=openai)

Embeddings are cached on disk in .recall/embed_cache/ keyed by sha256(text)
to avoid redundant computation.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np

# Dimensionality of the all-MiniLM-L6-v2 model
LOCAL_EMBEDDING_DIM = 384
# Dimensionality of text-embedding-3-small
OPENAI_EMBEDDING_DIM = 1536

_model = None
_cache_dir: Path | None = None


def _get_cache_dir() -> Path:
    """Return the embedding cache directory, creating it if needed."""
    global _cache_dir
    if _cache_dir is None:
        _cache_dir = Path(".recall") / "embed_cache"
        _cache_dir.mkdir(parents=True, exist_ok=True)
    return _cache_dir


def _cache_key(text: str) -> str:
    """Compute a cache key from the text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_from_cache(key: str) -> np.ndarray | None:
    """Load a cached embedding if it exists."""
    path = _get_cache_dir() / f"{key}.npy"
    if path.exists():
        return np.load(path)  # type: ignore[no-any-return]
    return None


def _save_to_cache(key: str, vec: np.ndarray) -> None:
    """Persist an embedding to the cache."""
    path = _get_cache_dir() / f"{key}.npy"
    np.save(path, vec)


def _use_openai() -> bool:
    """Check whether to use OpenAI embeddings."""
    return (
        os.environ.get("OPENAI_API_KEY") is not None
        and os.environ.get("RECALL_EMBEDDINGS", "").lower() == "openai"
    )


def _embed_local(text: str) -> np.ndarray:
    """Embed text using the local sentence-transformers model."""
    global _model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return _embed_fallback(text)

    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")

    vec = _model.encode(text, convert_to_numpy=True)
    return vec.astype(np.float32)  # type: ignore[no-any-return]


def _embed_openai(text: str) -> np.ndarray:
    """Embed text using OpenAI's text-embedding-3-small model."""
    from openai import OpenAI

    client = OpenAI()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    vec = np.array(response.data[0].embedding, dtype=np.float32)
    return vec


def _embed_fallback(text: str) -> np.ndarray:
    """Deterministic fallback embedding using character-level hashing.

    Used when sentence-transformers is not installed and OpenAI is not
    configured. Produces a 384-dim vector that preserves some semantic
    signal through character n-gram hashing. Not suitable for production
    but sufficient for testing and demos without network dependencies.
    """
    vec = np.zeros(LOCAL_EMBEDDING_DIM, dtype=np.float32)
    words = text.lower().split()
    for i, word in enumerate(words):
        for j in range(len(word)):
            # Use character trigrams for better semantic spread
            trigram = word[max(0, j - 1) : j + 2]
            h = int(hashlib.md5(trigram.encode()).hexdigest(), 16)
            idx = h % LOCAL_EMBEDDING_DIM
            vec[idx] += 1.0 / (1 + i * 0.1)
    # Normalize to unit vector
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def embed(text: str) -> np.ndarray:
    """Compute an embedding vector for the given text.

    Uses cached results when available. Backend selection:
      1. OpenAI text-embedding-3-small if OPENAI_API_KEY and RECALL_EMBEDDINGS=openai
      2. Local sentence-transformers/all-MiniLM-L6-v2 if installed
      3. Deterministic fallback (character n-gram hashing)

    Args:
        text: The text to embed.

    Returns:
        A numpy float32 array (384-dim for local/fallback, 1536-dim for OpenAI).
    """
    key = _cache_key(text)
    cached = _load_from_cache(key)
    if cached is not None:
        return cached

    vec = _embed_openai(text) if _use_openai() else _embed_local(text)

    _save_to_cache(key, vec)
    return vec


def embedding_to_bytes(vec: np.ndarray) -> bytes:
    """Serialize a numpy embedding vector to bytes for storage."""
    return vec.tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """Deserialize bytes back to a numpy embedding vector."""
    return np.frombuffer(data, dtype=np.float32).copy()  # type: ignore[no-any-return]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First embedding vector.
        b: Second embedding vector.

    Returns:
        Cosine similarity in [-1, 1]. Returns 0.0 if either vector is zero.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def reset_cache() -> None:
    """Clear the in-memory model cache. Useful for testing."""
    global _model, _cache_dir
    _model = None
    _cache_dir = None
