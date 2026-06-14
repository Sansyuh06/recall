"""Shared test fixtures and configuration for recall tests.

All tests use a temporary SQLite database that is cleaned up after
each test. Network-dependent tests are marked with @pytest.mark.network
and can be skipped with --no-network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from recall.embeddings import embedding_to_bytes, reset_cache
from recall.store.base import Atom
from recall.store.sqlite import SQLiteStore


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --no-network CLI flag to skip network-dependent tests."""
    parser.addoption(
        "--no-network",
        action="store_true",
        default=False,
        help="Skip tests that require network access",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "network: marks tests requiring network access")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip network tests when --no-network is passed."""
    if config.getoption("--no-network"):
        skip_network = pytest.mark.skip(reason="--no-network flag set")
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip_network)


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    """Create a temporary database path."""
    return str(tmp_path / "test_recall.db")


@pytest.fixture
def store(tmp_db: str) -> SQLiteStore:
    """Create a fresh SQLite store for each test."""
    s = SQLiteStore(tmp_db)
    yield s
    s.close()


@pytest.fixture
def sample_embedding() -> bytes:
    """Create a sample 384-dim embedding vector as bytes."""
    vec = np.random.RandomState(42).randn(384).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    return embedding_to_bytes(vec)


@pytest.fixture
def similar_embeddings() -> list[bytes]:
    """Create a set of similar embedding vectors for cluster testing.

    Returns 7 vectors that are very similar to each other (cosine >= 0.82).
    """
    rng = np.random.RandomState(42)
    base = rng.randn(384).astype(np.float32)
    base = base / np.linalg.norm(base)

    embeddings = []
    for _ in range(7):
        noise = rng.randn(384).astype(np.float32) * 0.1
        vec = base + noise
        vec = vec / np.linalg.norm(vec)
        embeddings.append(embedding_to_bytes(vec))

    return embeddings


@pytest.fixture
def dissimilar_embeddings() -> list[bytes]:
    """Create a set of dissimilar embedding vectors."""
    rng = np.random.RandomState(99)
    embeddings = []
    for _ in range(5):
        vec = rng.randn(384).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        embeddings.append(embedding_to_bytes(vec))
    return embeddings


@pytest.fixture
def populated_store(store: SQLiteStore, similar_embeddings: list[bytes]) -> SQLiteStore:
    """Create a store pre-populated with similar atoms for promotion testing."""
    now = datetime.now(UTC)

    for i, emb in enumerate(similar_embeddings):
        atom = Atom(
            id=f"atom_{i:03d}",
            prompt=f"How does authentication work in system {i}?",
            answer=(
                "Authentication uses token-based auth with Azure AD. "
                "The DefaultAzureCredential chain tries managed identity first, "
                "then falls back to CLI credentials."
            ),
            embedding=emb,
            agent_id="test_agent",
            written_at=now - timedelta(days=i),
            last_recalled_at=now - timedelta(days=i % 3),
            recall_count=5 - i,
        )
        store.write_atom(atom)

    return store


@pytest.fixture
def seed_corpus_path() -> Path:
    """Return the path to the test seed corpus."""
    return Path(__file__).parent / "fixtures" / "seed_corpus"


@pytest.fixture(autouse=True)
def clean_embed_cache() -> None:
    """Reset the embedding cache between tests."""
    reset_cache()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no API keys leak into tests."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RECALL_EMBEDDINGS", raising=False)
    monkeypatch.delenv("FOUNDRY_IQ_PROJECT", raising=False)
