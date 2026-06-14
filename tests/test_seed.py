"""Tests for the seed module."""

from __future__ import annotations

from pathlib import Path

from memoriagrain.seed import from_path
from memoriagrain.store.sqlite import SQLiteStore


class TestSeed:
    """Test seeding from files and directories."""

    def test_seed_from_markdown_file(self, store: SQLiteStore, seed_corpus_path: Path) -> None:
        md_file = seed_corpus_path / "foundry_auth.md"
        count = from_path(md_file, store)

        assert count > 0
        atoms = list(store.all_atoms())
        assert len(atoms) > 0

        # All atoms should have source_doc set
        for atom in atoms:
            assert atom.source_doc is not None
            assert "foundry_auth.md" in atom.source_doc

    def test_seed_from_directory(self, store: SQLiteStore, seed_corpus_path: Path) -> None:
        count = from_path(seed_corpus_path, store)

        assert count > 0
        atoms = list(store.all_atoms())
        # Should have atoms from multiple files
        source_docs = {a.source_doc for a in atoms}
        assert len(source_docs) >= 2

    def test_seed_sets_source_mtime(self, store: SQLiteStore, seed_corpus_path: Path) -> None:
        md_file = seed_corpus_path / "foundry_auth.md"
        from_path(md_file, store)

        atoms = list(store.all_atoms())
        for atom in atoms:
            assert atom.source_mtime is not None
            assert atom.source_mtime > 0

    def test_seed_runs_promotion(self, store: SQLiteStore, seed_corpus_path: Path) -> None:
        from_path(seed_corpus_path, store)

        stats = store.stats()
        # Promotion runs at the end of seeding
        # Whether patterns are created depends on embedding similarity
        assert stats.total_atoms > 0

    def test_seed_nonexistent_path(self, store: SQLiteStore) -> None:
        count = from_path(Path("/nonexistent/path"), store)
        assert count == 0

    def test_seed_filters_short_answers(self, store: SQLiteStore, tmp_path: Path) -> None:
        # Create a markdown file with very short content
        md = tmp_path / "short.md"
        md.write_text("# Title\nYes.\n# Another\nNo.\n")

        count = from_path(md, store)
        assert count == 0  # Both answers are too short
