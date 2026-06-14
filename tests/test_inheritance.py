"""Tests for the cross-agent inheritance module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from memoriagrain.inheritance import format_inheritance_line
from memoriagrain.store.base import Memory


class TestInheritance:
    """Test cross-agent inheritance line formatting."""

    def test_no_inheritance_same_agent(self) -> None:
        now = datetime.now(UTC)
        memories = [
            Memory(
                memory="test",
                grain="atom",
                confidence=0.5,
                freshness="fresh",
                derived_from=[],
                written_at=now.isoformat(),
                last_recalled_at=None,
                agent_id="my_agent",
                id="a1",
            )
        ]
        result = format_inheritance_line(memories, "my_agent")
        assert result is None

    def test_inheritance_from_foreign_agent(self) -> None:
        now = datetime.now(UTC)
        memories = [
            Memory(
                memory="foreign knowledge",
                grain="pattern",
                confidence=0.8,
                freshness="fresh",
                derived_from=["a1", "a2"],
                written_at=now.isoformat(),
                last_recalled_at=None,
                agent_id="agent_search",
                id="p1",
            ),
            Memory(
                memory="more foreign",
                grain="pattern",
                confidence=0.7,
                freshness="fresh",
                derived_from=["a3"],
                written_at=now.isoformat(),
                last_recalled_at=None,
                agent_id="agent_search",
                id="p2",
            ),
        ]
        result = format_inheritance_line(memories, "agent_review")
        assert result is not None
        assert "2" in result
        assert "agent_search" in result
        assert "inherited" in result

    def test_mixed_agents(self) -> None:
        now = datetime.now(UTC)
        memories = [
            Memory(
                memory="my own",
                grain="atom",
                confidence=0.5,
                freshness="fresh",
                derived_from=[],
                written_at=now.isoformat(),
                last_recalled_at=None,
                agent_id="my_agent",
                id="a1",
            ),
            Memory(
                memory="from search",
                grain="pattern",
                confidence=0.8,
                freshness="fresh",
                derived_from=[],
                written_at=now.isoformat(),
                last_recalled_at=None,
                agent_id="agent_search",
                id="p1",
            ),
        ]
        result = format_inheritance_line(memories, "my_agent")
        assert result is not None
        assert "agent_search" in result
        assert "1" in result

    def test_age_formatting(self) -> None:
        old = datetime.now(UTC) - timedelta(days=5)
        memories = [
            Memory(
                memory="old stuff",
                grain="atom",
                confidence=0.5,
                freshness="fresh",
                derived_from=[],
                written_at=old.isoformat(),
                last_recalled_at=None,
                agent_id="other_agent",
                id="a1",
            ),
        ]
        result = format_inheritance_line(memories, "my_agent")
        assert result is not None
        assert "5 days ago" in result

    def test_empty_memories(self) -> None:
        result = format_inheritance_line([], "my_agent")
        assert result is None
