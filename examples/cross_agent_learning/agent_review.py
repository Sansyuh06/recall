"""Agent B: Review agent that inherits from Agent A.

Queries the shared store for knowledge about a related topic.
The output shows the inheritance line, demonstrating that Agent B
discovered Agent A's patterns visibly and with attribution.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from memoriagrain.tool import handle_recall_call
from memoriagrain.store.sqlite import SQLiteStore


def main(db_path: str) -> None:
    """Run the review agent, querying the shared store."""
    store = SQLiteStore(db_path)

    print("Agent Review: Checking shared memory...")
    print()

    question = "What do I need to know about Foundry IQ authentication and document storage?"

    print(f"  Q: {question}")
    print()

    result = handle_recall_call(
        store,
        {"query": question, "grain": "auto"},
        agent_id="agent_review",
    )

    memory = str(result.get("memory", ""))
    grain = result.get("grain", "unknown")
    confidence = float(result.get("confidence", 0))
    inheritance = result.get("inheritance_note", "")

    if inheritance:
        print(f"  {inheritance}")
    print(f"  Recalled ({grain}, confidence={confidence:.2f}):")
    print(f"  {memory[:200]}...")
    print()

    stats = store.stats()
    print(f"Agent Review done. Store: {stats.total_atoms} atoms, {stats.total_patterns} patterns.")
    store.close()


if __name__ == "__main__":
    import tempfile

    db = os.path.join(tempfile.mkdtemp(), "shared.db")
    # In standalone mode, run agent_search first
    from examples.cross_agent_learning.agent_search import main as search_main

    search_main(db)
    print("\n" + "=" * 60 + "\n")
    main(db)
