"""recall() tool injection logic.

Provides the tool definition (OpenAI function-calling format) and the
handler that performs the actual retrieval. This is the core of what
makes recall a tool the model calls, rather than a prefix injection.

The model sees `recall` in its tool list, decides when to call it,
and gets back a provenance-rich response. The recall step appears
in the trace. Memory becomes auditable.
"""

from __future__ import annotations

from recall.confidence import confidence as compute_confidence
from recall.embeddings import embed, embedding_to_bytes
from recall.freshness import check_freshness
from recall.inheritance import emit_inheritance_line, format_inheritance_line
from recall.store.base import Memory, Store


def recall_tool_definition() -> dict[str, object]:
    """Return the OpenAI-style function spec for the recall tool.

    This is the tool definition injected into the agent's tool list.
    The model calls it when it wants to remember something.
    """
    return {
        "type": "function",
        "function": {
            "name": "recall",
            "description": (
                "Recall what this agent (or related agents) has learned "
                "about similar questions. Returns memories with provenance, "
                "confidence, and freshness metadata."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search memory for.",
                    },
                    "grain": {
                        "type": "string",
                        "enum": ["auto", "atom", "pattern", "principle"],
                        "default": "auto",
                        "description": (
                            "Memory grain level. 'auto' tries principles first, "
                            "then patterns, then atoms."
                        ),
                    },
                    "max_tokens": {
                        "type": "integer",
                        "default": 500,
                        "description": "Maximum tokens of memory to return.",
                    },
                },
                "required": ["query"],
            },
        },
    }


def handle_recall_call(
    store: Store,
    args: dict[str, object],
    agent_id: str = "default",
    k: int = 5,
) -> dict[str, object]:
    """Handle a recall tool call from the model.

    Performs embedding-based search, applies freshness checking and
    confidence scoring, truncates to max_tokens, and formats the
    response with full provenance.

    Args:
        store: The storage backend.
        args: The tool call arguments from the model.
        agent_id: The current agent's ID (for inheritance detection).
        k: Maximum number of raw results to retrieve.

    Returns:
        A dict matching the recall response schema.
    """
    query = str(args.get("query", ""))
    grain = str(args.get("grain", "auto"))
    max_tokens = int(str(args.get("max_tokens", 500)))

    if not query:
        return _empty_response()

    # Embed the query
    query_vec = embed(query)
    query_bytes = embedding_to_bytes(query_vec)

    # Search the store
    memories = store.search(query_bytes, grain=grain, k=k)

    if not memories:
        return _empty_response()

    # Enrich with freshness and confidence
    for mem in memories:
        if mem.grain == "atom" and mem.source_doc:
            atom = store.get_atom(mem.id)
            if atom:
                mem.freshness = check_freshness(atom)
        mem.confidence = compute_confidence(mem)

    # Check for cross-agent inheritance
    inheritance_note = format_inheritance_line(memories, agent_id)
    if inheritance_note:
        emit_inheritance_line(inheritance_note)

    # Apply max_tokens truncation
    truncated_at: str | None = None
    combined_text = ""
    selected_memories: list[Memory] = []

    for mem in memories:
        token_estimate = len(mem.memory.split())
        if len(combined_text.split()) + token_estimate > max_tokens:
            truncated_at = f"Truncated at {max_tokens} tokens ({len(selected_memories)} of {len(memories)} results)"
            break
        combined_text += mem.memory + "\n\n"
        selected_memories.append(mem)

    if not selected_memories and memories:
        # Always return at least one result, even if truncated
        first = memories[0]
        words = first.memory.split()[:max_tokens]
        first_truncated = Memory(
            memory=" ".join(words),
            grain=first.grain,
            confidence=first.confidence,
            freshness=first.freshness,
            derived_from=first.derived_from,
            written_at=first.written_at,
            last_recalled_at=first.last_recalled_at,
            source_doc=first.source_doc,
            truncated_at=f"Truncated single result to {max_tokens} tokens",
            agent_id=first.agent_id,
            id=first.id,
        )
        selected_memories = [first_truncated]
        truncated_at = first_truncated.truncated_at

    # Build response from the best match
    best = selected_memories[0]
    all_derived: list[str] = []
    for m in selected_memories:
        all_derived.extend(m.derived_from)

    response: dict[str, object] = {
        "memory": combined_text.strip(),
        "grain": best.grain,
        "confidence": best.confidence,
        "freshness": best.freshness,
        "derived_from": list(dict.fromkeys(all_derived)),  # dedupe preserving order
        "written_at": best.written_at,
        "last_recalled_at": best.last_recalled_at,
        "source_doc": best.source_doc,
        "truncated_at": truncated_at,
    }

    if inheritance_note:
        response["inheritance_note"] = inheritance_note

    return response


def _empty_response() -> dict[str, object]:
    """Return an empty recall response."""
    return {
        "memory": "",
        "grain": "atom",
        "confidence": 0.0,
        "freshness": "unknown",
        "derived_from": [],
        "written_at": "",
        "last_recalled_at": None,
        "source_doc": None,
        "truncated_at": None,
    }
