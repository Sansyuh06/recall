"""Pre-tool hook for recall -- redundant call detection.

Optional hook that checks if a tool call is about to happen for a
question very similar to a past one. If yes, injects a hint message
before the tool fires.

Off by default; enabled via: recall config set hooks.pre_tool true
"""

from __future__ import annotations

from recall.embeddings import embed, embedding_to_bytes
from recall.store.base import Store


def check_redundant_call(
    store: Store,
    query: str,
    similarity_threshold: float = 0.85,
    min_recall_count: int = 3,
) -> str | None:
    """Check if a query is redundant based on past recall history.

    Args:
        store: The storage backend.
        query: The incoming query text.
        similarity_threshold: Cosine similarity threshold for match.
        min_recall_count: Minimum times a similar atom was recalled.

    Returns:
        A hint message if the query is redundant, None otherwise.
    """
    vec = embed(query)
    query_bytes = embedding_to_bytes(vec)

    memories = store.search(query_bytes, grain="atom", k=3)

    for mem in memories:
        if mem.confidence > similarity_threshold:
            atom = store.get_atom(mem.id)
            if atom and atom.recall_count >= min_recall_count:
                return (
                    f"[recall hint] You've answered a similar question "
                    f"{atom.recall_count} times recently. "
                    f"Last answer: {atom.answer[:200]}"
                )

    return None


def format_pre_tool_injection(hint: str) -> dict[str, str]:
    """Format the hint as a system message for injection.

    Args:
        hint: The hint text from check_redundant_call.

    Returns:
        A message dict suitable for injection into the conversation.
    """
    return {
        "role": "system",
        "content": hint,
    }
