"""Memory diff on agent redeploy.

Compares the current agent definition (system prompt, tools, model)
against the stored snapshot from the last deploy. For each stored
atom/pattern, checks whether the change invalidates it.

Usage:
    recall diff --against last-deploy
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from recall.judge import _judge_with_heuristic
from recall.store.base import Atom, Store

logger = logging.getLogger(__name__)

SNAPSHOT_PATH = Path(".recall") / "last_deploy.json"


@dataclass
class DiffResult:
    """A single memory that may be invalidated by a deploy change."""

    memory_id: str
    grain: str
    memory_text: str
    reason: str
    suggested_action: str  # "review" | "evict" | "keep"


def save_deploy_snapshot(
    system_prompt: str = "",
    tools: list[str] | None = None,
    model: str = "",
    extra: dict[str, str] | None = None,
) -> None:
    """Save a snapshot of the current agent configuration.

    Args:
        system_prompt: The agent's system prompt.
        tools: List of tool names the agent uses.
        model: The model identifier.
        extra: Additional metadata to snapshot.
    """
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "system_prompt": system_prompt,
        "tools": tools or [],
        "model": model,
        "extra": extra or {},
        "saved_at": datetime.now(UTC).isoformat(),
    }

    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    logger.info("Deploy snapshot saved to %s", SNAPSHOT_PATH)


def load_deploy_snapshot() -> dict[str, object] | None:
    """Load the last deploy snapshot.

    Returns:
        The snapshot dict, or None if no snapshot exists.
    """
    if not SNAPSHOT_PATH.exists():
        return None

    try:
        text = SNAPSHOT_PATH.read_text(encoding="utf-8")
        return json.loads(text)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load deploy snapshot: %s", e)
        return None


def diff_against_last_deploy(store: Store) -> list[DiffResult]:
    """Compare current memories against the last deploy snapshot.

    For each atom, checks whether changes to the agent definition
    (system prompt, tools, model) might invalidate the memory.

    Args:
        store: The storage backend.

    Returns:
        List of DiffResult objects for potentially invalidated memories.
    """
    snapshot = load_deploy_snapshot()
    if snapshot is None:
        logger.info("No deploy snapshot found. Run 'recall diff --save' first.")
        return []

    old_prompt = str(snapshot.get("system_prompt", ""))
    old_tools = snapshot.get("tools", [])
    old_model = str(snapshot.get("model", ""))

    results: list[DiffResult] = []

    for atom in store.all_atoms():
        if atom.decayed or atom.superseded_by:
            continue

        invalidation = _check_invalidation(atom, old_prompt, old_tools, old_model)
        if invalidation:
            results.append(invalidation)

    return results


def _check_invalidation(
    atom: Atom,
    old_prompt: str,
    old_tools: list[str] | object,
    old_model: str,
) -> DiffResult | None:
    """Check whether an atom might be invalidated by a deploy change.

    Uses a heuristic approach: if the atom's prompt or answer references
    concepts that changed between deploys, it may be stale.
    """
    # Build context about what changed
    atom_text = f"{atom.prompt} {atom.answer}".lower()

    # Check if atom references tools that no longer exist
    if isinstance(old_tools, list):
        for tool in old_tools:
            tool_name = str(tool).lower()
            if tool_name in atom_text:
                return DiffResult(
                    memory_id=atom.id,
                    grain="atom",
                    memory_text=atom.answer[:100],
                    reason=f"References tool '{tool}' which may have changed",
                    suggested_action="review",
                )

    # Check if atom answer is very similar to old system prompt
    # (suggesting it may be parroting prompt content that changed)
    if old_prompt and len(old_prompt) > 50:
        # Create pseudo-atoms for the heuristic judge
        from recall.store.base import Atom as PseudoAtom

        pseudo_prompt = PseudoAtom(prompt="old prompt", answer=old_prompt[:500])
        pseudo_atom = PseudoAtom(prompt=atom.prompt, answer=atom.answer)

        judgment = _judge_with_heuristic([pseudo_prompt, pseudo_atom])
        similarity = 1.0 - float(str(judgment.get("disagreement", 1.0)))

        if similarity > 0.7:
            return DiffResult(
                memory_id=atom.id,
                grain="atom",
                memory_text=atom.answer[:100],
                reason="High similarity to old system prompt content (may be outdated)",
                suggested_action="review",
            )

    return None
