"""Tests for the confidence scoring module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from recall.confidence import confidence
from recall.store.base import Memory


class TestConfidence:
    """Test the confidence formula."""

    def test_atom_base_confidence(self) -> None:
        now = datetime.now(UTC)
        mem = Memory(
            memory="test",
            grain="atom",
            confidence=0.5,
            freshness="fresh",
            derived_from=[],
            written_at=now.isoformat(),
            last_recalled_at=now.isoformat(),
        )
        score = confidence(mem)
        # Atom base (0.5) * recency (~1.0) * agreement (1.0 for atoms)
        assert 0.4 <= score <= 0.55

    def test_pattern_higher_than_atom(self) -> None:
        now = datetime.now(UTC)
        atom_mem = Memory(
            memory="test",
            grain="atom",
            confidence=0.5,
            freshness="fresh",
            derived_from=[],
            written_at=now.isoformat(),
            last_recalled_at=now.isoformat(),
        )
        pattern_mem = Memory(
            memory="test",
            grain="pattern",
            confidence=0.85,
            freshness="fresh",
            derived_from=["a1", "a2"],
            written_at=now.isoformat(),
            last_recalled_at=now.isoformat(),
        )
        assert confidence(pattern_mem) > confidence(atom_mem)

    def test_principle_highest_confidence(self) -> None:
        now = datetime.now(UTC)
        mem = Memory(
            memory="test",
            grain="principle",
            confidence=0.95,
            freshness="fresh",
            derived_from=["p1", "p2"],
            written_at=now.isoformat(),
            last_recalled_at=now.isoformat(),
        )
        score = confidence(mem)
        # Principle base (0.9) * recency (~1.0) * agreement (0.95)
        assert score > 0.7

    def test_recency_decay(self) -> None:
        now = datetime.now(UTC)
        old = now - timedelta(days=60)

        recent = Memory(
            memory="test",
            grain="atom",
            confidence=0.5,
            freshness="fresh",
            derived_from=[],
            written_at=now.isoformat(),
            last_recalled_at=now.isoformat(),
        )
        stale = Memory(
            memory="test",
            grain="atom",
            confidence=0.5,
            freshness="stale",
            derived_from=[],
            written_at=old.isoformat(),
            last_recalled_at=old.isoformat(),
        )
        assert confidence(recent) > confidence(stale)

    def test_confidence_bounded(self) -> None:
        mem = Memory(
            memory="test",
            grain="principle",
            confidence=1.0,
            freshness="fresh",
            derived_from=[],
            written_at=datetime.now(UTC).isoformat(),
            last_recalled_at=datetime.now(UTC).isoformat(),
        )
        score = confidence(mem)
        assert 0.0 <= score <= 1.0
