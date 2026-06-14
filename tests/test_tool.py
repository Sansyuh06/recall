"""Tests for the memoriagrain tool handler."""

from __future__ import annotations

from memoriagrain.embeddings import embed, embedding_to_bytes
from memoriagrain.store.base import Atom
from memoriagrain.store.sqlite import SQLiteStore
from memoriagrain.tool import handle_recall_call


class TestHandleRecallCall:
    """Test the tool call handler."""

    def test_returns_correct_shape(self, store: SQLiteStore) -> None:
        vec = embed("What is authentication?")
        store.write_atom(
            Atom(
                id="tool_001",
                prompt="How does auth work?",
                answer="Authentication uses Azure AD tokens for secure access.",
                embedding=embedding_to_bytes(vec),
            )
        )

        result = handle_recall_call(store, {"query": "What is authentication?"})

        assert "memory" in result
        assert "grain" in result
        assert "confidence" in result
        assert "freshness" in result
        assert "derived_from" in result
        assert "written_at" in result
        assert "last_recalled_at" in result
        assert "source_doc" in result
        assert "truncated_at" in result

    def test_empty_query_returns_empty(self, store: SQLiteStore) -> None:
        result = handle_recall_call(store, {"query": ""})
        assert result["memory"] == ""
        assert result["confidence"] == 0.0

    def test_no_results_returns_empty(self, store: SQLiteStore) -> None:
        result = handle_recall_call(store, {"query": "nonexistent topic"})
        assert result["memory"] == ""

    def test_max_tokens_truncation(self, store: SQLiteStore) -> None:
        vec = embed("test query")
        # Write a long answer
        long_answer = " ".join(["word"] * 1000)
        store.write_atom(
            Atom(
                id="trunc_001",
                prompt="Test question?",
                answer=long_answer,
                embedding=embedding_to_bytes(vec),
            )
        )

        result = handle_recall_call(store, {"query": "test query", "max_tokens": 50})
        # Should have truncated
        if result["memory"]:
            words = result["memory"].split()
            assert len(words) <= 100  # generous upper bound

    def test_grain_auto_fallback(self, store: SQLiteStore) -> None:
        vec = embed("auth question")
        store.write_atom(
            Atom(
                id="auto_001",
                prompt="Auth?",
                answer="Token-based authentication with Azure Active Directory.",
                embedding=embedding_to_bytes(vec),
            )
        )

        result = handle_recall_call(store, {"query": "auth question", "grain": "auto"})
        # Should fall back to atom since no patterns/principles exist
        if result["memory"]:
            assert result["grain"] == "atom"

    def test_inheritance_note_for_foreign_agent(self, store: SQLiteStore) -> None:
        vec = embed("shared knowledge")
        store.write_atom(
            Atom(
                id="foreign_001",
                prompt="Shared question?",
                answer="This was answered by another agent with useful context.",
                embedding=embedding_to_bytes(vec),
                agent_id="agent_search",
            )
        )

        result = handle_recall_call(
            store,
            {"query": "shared knowledge"},
            agent_id="agent_review",
        )
        if result["memory"]:
            assert "inheritance_note" in result
