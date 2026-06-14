"""PostToolUse hook for Claude Code Stop event.

Standalone script invocable as a Claude Code hook that fires on session
Stop. Reads the session transcript from stdin, extracts Q->A turns,
and writes them as atoms with full session attribution.

Invoked by Claude Code as:
    python -m memoriagrain.hooks.claude_code_stop

Reads JSON transcript from stdin. Writes atoms to the configured store.
Prints a summary to stderr so it appears in the agent trace.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from memoriagrain.embeddings import embed, embedding_to_bytes
from memoriagrain.store.base import Atom, Store
from memoriagrain.store.sqlite import SQLiteStore


def extract_qa_pairs(transcript: list[dict[str, object]]) -> list[tuple[str, str]]:
    """Extract question-answer pairs from a session transcript.

    Pairs are formed from consecutive user->assistant message pairs.
    Filters out:
      - Answers shorter than 50 characters
      - User messages that are clarification questions (ending in '?'
        with fewer than 20 characters)
      - Turns where the assistant response indicates an error

    Args:
        transcript: List of message dicts with 'role' and 'content' keys.

    Returns:
        List of (question, answer) tuples.
    """
    pairs: list[tuple[str, str]] = []

    i = 0
    while i < len(transcript) - 1:
        msg = transcript[i]
        next_msg = transcript[i + 1]

        role = str(msg.get("role", ""))
        next_role = str(next_msg.get("role", ""))
        content = str(msg.get("content", ""))
        next_content = str(next_msg.get("content", ""))

        if role == "user" and next_role == "assistant":
            # Filter: skip short clarification questions
            if len(content.strip()) < 20 and content.strip().endswith("?"):
                i += 1
                continue

            # Filter: skip short answers
            if len(next_content.strip()) < 50:
                i += 2
                continue

            # Filter: skip error responses — only when the first line
            # starts with an actual error marker, not just any mention
            # of the word "error" in legitimate content.
            first_line = next_content.strip().split("\n")[0].lower()
            if (
                first_line.startswith("error:")
                or first_line.startswith("traceback (most recent call last):")
                or first_line.startswith("exception:")
            ):
                i += 2
                continue

            pairs.append((content.strip(), next_content.strip()))
            i += 2
        else:
            i += 1

    return pairs


def process_transcript(
    transcript_data: dict[str, object],
    store: Store | None = None,
) -> int:
    """Process a Claude Code session transcript and write atoms.

    Args:
        transcript_data: The full transcript JSON object.
            Expected shape: {"session_id": str, "messages": [...]}
        store: The storage backend. Defaults to SQLiteStore.

    Returns:
        Number of atoms written.
    """
    if store is None:
        store = SQLiteStore()

    session_id = str(transcript_data.get("session_id", "unknown"))
    messages = transcript_data.get("messages", [])

    if not isinstance(messages, list):
        return 0

    pairs = extract_qa_pairs(messages)

    count = 0
    for prompt, answer in pairs:
        combined = f"{prompt} {answer}"
        vec = embed(combined)

        atom = Atom(
            prompt=prompt,
            answer=answer,
            embedding=embedding_to_bytes(vec),
            agent_id=f"claude_code_{session_id}",
            written_at=datetime.now(UTC),
            source_doc=f"session:{session_id}",
        )
        store.write_atom(atom)
        count += 1

    return count


def main() -> None:
    """Entry point for the Claude Code Stop hook.

    Reads transcript JSON from stdin and writes atoms to the store.
    """
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        data = json.loads(raw)
        count = process_transcript(data)

        if count > 0:
            session_id = data.get("session_id", "unknown")
            print(
                f"[memoriagrain] wrote {count} atoms from session {session_id}",
                file=sys.stderr,
            )

    except json.JSONDecodeError as e:
        print(f"[memoriagrain] failed to parse transcript: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[memoriagrain] hook error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
