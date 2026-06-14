"""Cross-agent memory inheritance for recall.

When memories are recalled from agents other than the current one,
this module formats a visible attribution line for the agent trace.
The inheritance line is printed to stderr and included in the response
payload so that both the agent and the human reviewing the trace can
see where knowledge came from.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from recall.store.base import Memory


def format_inheritance_line(memories: list[Memory], current_agent: str) -> str | None:
    """Format a one-line inheritance attribution string.

    Args:
        memories: The memories being returned to the agent.
        current_agent: The ID of the currently running agent.

    Returns:
        A string like '3 patterns inherited from agent_search (written 2 days ago)'
        or None if all memories are from the current agent.
    """
    foreign: dict[str, list[Memory]] = {}
    for mem in memories:
        if mem.agent_id and mem.agent_id != current_agent:
            foreign.setdefault(mem.agent_id, []).append(mem)

    if not foreign:
        return None

    parts: list[str] = []
    for agent_id, mems in foreign.items():
        count = len(mems)
        grains = set(m.grain for m in mems)
        grain_label = "/".join(sorted(grains))
        noun = grain_label if count == 1 else f"{grain_label}s"

        # Find the most recent written_at among the foreign memories
        age_str = _format_age(mems)

        parts.append(f"{count} {noun} inherited from {agent_id}{age_str}")

    return "\xf0\x9f\xa7\xa0 " + "; ".join(parts)


def _format_age(memories: list[Memory]) -> str:
    """Format a relative age string from the newest memory's written_at."""
    newest_dt: datetime | None = None
    for mem in memories:
        if mem.written_at:
            try:
                dt = datetime.fromisoformat(mem.written_at)
                if newest_dt is None or dt > newest_dt:
                    newest_dt = dt
            except (ValueError, TypeError):
                continue

    if newest_dt is None:
        return ""

    age = datetime.now(UTC) - newest_dt
    days = age.days

    if days == 0:
        hours = int(age.total_seconds() / 3600)
        if hours == 0:
            return " (written just now)"
        return f" (written {hours}h ago)"
    elif days == 1:
        return " (written yesterday)"
    else:
        return f" (written {days} days ago)"


def emit_inheritance_line(line: str) -> None:
    """Print an inheritance line to stderr for trace visibility.

    Args:
        line: The formatted inheritance string.
    """
    print(line, file=sys.stderr)
