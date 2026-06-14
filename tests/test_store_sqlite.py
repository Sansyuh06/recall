"""Tests for the SQLite storage backend."""

from __future__ import annotations

from recall.store.base import Atom, Pattern, Principle
from recall.store.sqlite import SQLiteStore


class TestSQLiteStoreCRUD:
    """Test basic CRUD operations on the SQLite store."""

    def test_write_and_get_atom(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        atom = Atom(
            id="test_001",
            prompt="What is recall?",
            answer="A memory system for AI agents.",
            embedding=sample_embedding,
            agent_id="test",
        )
        returned_id = store.write_atom(atom)
        assert returned_id == "test_001"

        retrieved = store.get("test_001")
        assert retrieved is not None
        assert retrieved.grain == "atom"
        assert "What is recall?" in retrieved.memory

    def test_write_and_get_pattern(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        pattern = Pattern(
            id="pat_001",
            text="Authentication uses token-based auth with Azure AD.",
            embedding=sample_embedding,
            derived_from=["atom_001", "atom_002"],
            confidence=0.85,
        )
        returned_id = store.write_pattern(pattern)
        assert returned_id == "pat_001"

        retrieved = store.get("pat_001")
        assert retrieved is not None
        assert retrieved.grain == "pattern"
        assert retrieved.confidence == 0.85
        assert retrieved.derived_from == ["atom_001", "atom_002"]

    def test_write_and_get_principle(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        principle = Principle(
            id="prin_001",
            text="All API access requires authentication.",
            embedding=sample_embedding,
            derived_from=["pat_001", "pat_002"],
            confidence=0.92,
        )
        returned_id = store.write_principle(principle)
        assert returned_id == "prin_001"

        retrieved = store.get("prin_001")
        assert retrieved is not None
        assert retrieved.grain == "principle"
        assert retrieved.confidence == 0.92

    def test_get_nonexistent_returns_none(self, store: SQLiteStore) -> None:
        assert store.get("nonexistent") is None

    def test_delete_atom(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        atom = Atom(id="del_001", prompt="test", answer="test", embedding=sample_embedding)
        store.write_atom(atom)
        assert store.get("del_001") is not None

        store.delete("del_001")
        assert store.get("del_001") is None

    def test_update_atom(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        atom = Atom(
            id="upd_001",
            prompt="original question",
            answer="original answer",
            embedding=sample_embedding,
        )
        store.write_atom(atom)

        atom.answer = "updated answer"
        atom.recall_count = 5
        store.update_atom(atom)

        retrieved = store.get_atom("upd_001")
        assert retrieved is not None
        assert retrieved.answer == "updated answer"
        assert retrieved.recall_count == 5

    def test_all_atoms_iterator(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        for i in range(5):
            atom = Atom(
                id=f"iter_{i:03d}",
                prompt=f"Question {i}",
                answer=f"Answer {i}",
                embedding=sample_embedding,
            )
            store.write_atom(atom)

        atoms = list(store.all_atoms())
        assert len(atoms) == 5


class TestSQLiteStoreSearch:
    """Test embedding-based search functionality."""

    def test_search_by_cosine_similarity(
        self, store: SQLiteStore, similar_embeddings: list[bytes]
    ) -> None:
        for i, emb in enumerate(similar_embeddings[:3]):
            atom = Atom(
                id=f"search_{i:03d}",
                prompt=f"Auth question {i}",
                answer=f"Auth answer {i}",
                embedding=emb,
            )
            store.write_atom(atom)

        results = store.search(similar_embeddings[0], grain="atom", k=3)
        assert len(results) > 0
        assert results[0].grain == "atom"

    def test_search_auto_grain_fallback(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        atom = Atom(
            id="auto_001",
            prompt="Test Q",
            answer="Test A",
            embedding=sample_embedding,
        )
        store.write_atom(atom)

        results = store.search(sample_embedding, grain="auto", k=3)
        assert len(results) > 0
        assert results[0].grain == "atom"

    def test_search_empty_store(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        results = store.search(sample_embedding, grain="atom", k=5)
        assert results == []

    def test_search_updates_recall_count(self, store: SQLiteStore, sample_embedding: bytes) -> None:
        atom = Atom(
            id="rc_001",
            prompt="Test",
            answer="Test answer",
            embedding=sample_embedding,
        )
        store.write_atom(atom)

        store.search(sample_embedding, grain="atom", k=1)

        updated = store.get_atom("rc_001")
        assert updated is not None
        assert updated.recall_count == 1


class TestSQLiteStoreStats:
    """Test store statistics."""

    def test_stats_empty_store(self, store: SQLiteStore) -> None:
        st = store.stats()
        assert st.total_atoms == 0
        assert st.total_patterns == 0
        assert st.total_principles == 0

    def test_stats_populated_store(self, populated_store: SQLiteStore) -> None:
        st = populated_store.stats()
        assert st.total_atoms == 7
        assert st.total_patterns == 0
        assert "test_agent" in st.agents

    def test_config_get_set(self, store: SQLiteStore) -> None:
        store.set_config("promotion.strictness", "strict")
        assert store.get_config("promotion.strictness") == "strict"

    def test_config_default(self, store: SQLiteStore) -> None:
        assert store.get_config("nonexistent", "default_val") == "default_val"
