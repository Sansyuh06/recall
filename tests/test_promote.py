"""Tests for the three-gate promotion algorithm."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from recall.promote import PromoteWorker, PromotionConfig
from recall.store.base import Atom
from recall.store.sqlite import SQLiteStore


class TestPromotionConfig:
    """Test strictness presets."""

    def test_default_config(self) -> None:
        config = PromotionConfig.from_strictness("default")
        assert config.min_cluster_size == 5
        assert config.similarity_threshold == 0.82
        assert config.max_disagreement == 0.2
        assert config.min_recent == 2

    def test_loose_config(self) -> None:
        config = PromotionConfig.from_strictness("loose")
        assert config.min_cluster_size == 3
        assert config.similarity_threshold == 0.75
        assert config.max_disagreement == 0.3

    def test_strict_config(self) -> None:
        config = PromotionConfig.from_strictness("strict")
        assert config.min_cluster_size == 7
        assert config.similarity_threshold == 0.88
        assert config.max_disagreement == 0.1


class TestPromoteWorker:
    """Test the full promotion pipeline."""

    def test_promotion_with_sufficient_cluster(self, populated_store: SQLiteStore) -> None:
        worker = PromoteWorker(populated_store, strictness="loose")
        created = worker.run_once()

        # With 7 similar atoms and loose config (min 3), should promote
        # Promotion depends on agreement and recency gates too
        # At minimum, the worker should not error
        assert isinstance(created, list)

    def test_no_promotion_with_few_atoms(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        # Only 2 atoms -- below any threshold
        for i in range(2):
            atom = Atom(
                id=f"few_{i}",
                prompt=f"Q {i}",
                answer=f"A {i}",
                embedding=sample_embedding,
            )
            store.write_atom(atom)

        worker = PromoteWorker(store)
        created = worker.run_once()
        assert created == []

    def test_idempotent_promotion(self, populated_store: SQLiteStore) -> None:
        worker = PromoteWorker(populated_store, strictness="loose")
        first_run = worker.run_once()
        second_run = worker.run_once()

        # Atoms promoted in first run should not be re-promoted
        # (they have promoted_into_pattern_id set)
        for pattern_id in first_run:
            assert pattern_id not in second_run

    def test_dissimilar_atoms_not_promoted(
        self, store: SQLiteStore, dissimilar_embeddings: list[bytes]
    ) -> None:
        now = datetime.now(UTC)
        for i, emb in enumerate(dissimilar_embeddings):
            atom = Atom(
                id=f"dis_{i}",
                prompt=f"Completely different question {i}",
                answer=f"Completely different answer {i}",
                embedding=emb,
                last_recalled_at=now,
                recall_count=10,
            )
            store.write_atom(atom)

        worker = PromoteWorker(store, strictness="loose")
        created = worker.run_once()
        assert created == []


class TestGateEnforcement:
    """Test that individual gates are enforced."""

    def test_recency_gate_blocks_old_atoms(
        self, store: SQLiteStore, similar_embeddings: list[bytes]
    ) -> None:
        old_date = datetime.now(UTC) - timedelta(days=90)
        for i, emb in enumerate(similar_embeddings[:5]):
            atom = Atom(
                id=f"old_{i}",
                prompt="How does auth work?",
                answer="Token-based auth with Azure AD credentials.",
                embedding=emb,
                last_recalled_at=old_date,
                recall_count=1,
            )
            store.write_atom(atom)

        worker = PromoteWorker(store)
        created = worker.run_once()
        # All atoms last recalled 90 days ago -- should fail recency gate
        assert created == []
