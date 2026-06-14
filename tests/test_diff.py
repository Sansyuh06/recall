"""Tests for the diff module."""

from __future__ import annotations

import json
from pathlib import Path

from recall.diff import (
    diff_against_last_deploy,
    load_deploy_snapshot,
    save_deploy_snapshot,
)
from recall.embeddings import embed, embedding_to_bytes
from recall.store.base import Atom
from recall.store.sqlite import SQLiteStore


class TestDiff:
    """Test memory diff against deploy snapshots."""

    def test_save_and_load_snapshot(self, tmp_path: Path, monkeypatch: object) -> None:
        import recall.diff as diff_module

        monkeypatch.setattr(diff_module, "SNAPSHOT_PATH", tmp_path / "snapshot.json")  # type: ignore[attr-defined]

        save_deploy_snapshot(
            system_prompt="You are a helpful agent.",
            tools=["search", "recall"],
            model="gpt-4o",
        )

        snapshot = load_deploy_snapshot()
        assert snapshot is not None
        assert snapshot["system_prompt"] == "You are a helpful agent."
        assert snapshot["model"] == "gpt-4o"

    def test_no_snapshot_returns_empty(self, store: SQLiteStore) -> None:
        results = diff_against_last_deploy(store)
        assert results == []

    def test_diff_detects_tool_reference(
        self, store: SQLiteStore, tmp_path: Path, monkeypatch: object
    ) -> None:
        import recall.diff as diff_module

        snapshot_path = tmp_path / "snapshot.json"
        monkeypatch.setattr(diff_module, "SNAPSHOT_PATH", snapshot_path)  # type: ignore[attr-defined]

        # Save a snapshot with a tool
        snapshot = {
            "system_prompt": "test",
            "tools": ["deprecated_search"],
            "model": "gpt-4o",
            "extra": {},
            "saved_at": "2026-06-14T00:00:00Z",
        }
        snapshot_path.write_text(json.dumps(snapshot))

        # Write an atom that references the tool
        vec = embed("deprecated_search usage")
        store.write_atom(
            Atom(
                id="diff_001",
                prompt="How to search?",
                answer="Use the deprecated_search tool to find documents.",
                embedding=embedding_to_bytes(vec),
            )
        )

        results = diff_against_last_deploy(store)
        assert len(results) >= 1
        assert results[0].suggested_action == "review"
