"""Tests for the freshness checking module."""

from __future__ import annotations

import time
from pathlib import Path

from memoriagrain.freshness import check_freshness
from memoriagrain.store.base import Atom


class TestFreshness:
    """Test source-mtime freshness checking."""

    def test_fresh_when_mtime_matches(self, tmp_path: Path) -> None:
        source = tmp_path / "doc.md"
        source.write_text("original content")
        mtime = source.stat().st_mtime

        atom = Atom(
            source_doc=str(source),
            source_mtime=mtime,
        )
        assert check_freshness(atom) == "fresh"

    def test_stale_when_file_modified(self, tmp_path: Path) -> None:
        source = tmp_path / "doc.md"
        source.write_text("original content")
        mtime = source.stat().st_mtime

        atom = Atom(
            source_doc=str(source),
            source_mtime=mtime,
        )

        # Modify the file
        time.sleep(0.1)
        source.write_text("modified content")

        assert check_freshness(atom) == "stale"

    def test_unknown_when_no_source_doc(self) -> None:
        atom = Atom()
        assert check_freshness(atom) == "unknown"

    def test_unknown_when_file_missing(self) -> None:
        atom = Atom(
            source_doc="/nonexistent/file.md",
            source_mtime=12345.0,
        )
        assert check_freshness(atom) == "unknown"

    def test_unknown_when_no_stored_mtime(self, tmp_path: Path) -> None:
        source = tmp_path / "doc.md"
        source.write_text("content")

        atom = Atom(
            source_doc=str(source),
            source_mtime=None,
        )
        assert check_freshness(atom) == "unknown"
