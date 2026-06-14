"""Agent A: Search agent that learns from research.

Answers questions about a topic, writing each Q&A pair as an atom
to a shared SQLite store. Agent B (agent_review.py) will later
query the same store and see inherited knowledge.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from recall.embeddings import embed, embedding_to_bytes
from recall.store.base import Atom
from recall.store.sqlite import SQLiteStore

QUESTIONS = [
    "What authentication methods does Foundry IQ support?",
    "How are documents stored in a knowledge base?",
    "What is the recommended chunk size for embeddings?",
]

ANSWERS = [
    "Foundry IQ supports Azure AD authentication via DefaultAzureCredential, including managed identity, CLI credentials, and environment variables.",
    "Documents in Foundry IQ are stored with content (text), metadata (JSON), and an auto-computed embedding vector. They support CRUD operations via REST API.",
    "The recommended chunk size is 512 tokens with 64 tokens of overlap. This balances retrieval precision with context window efficiency.",
]


def main(db_path: str) -> None:
    """Run the search agent, writing atoms to the shared store."""
    store = SQLiteStore(db_path)

    print("Agent Search: Researching Foundry IQ...")
    print()

    for i, (question, answer) in enumerate(zip(QUESTIONS, ANSWERS)):
        print(f"  Q: {question}")
        print(f"  A: {answer[:80]}...")

        vec = embed(f"{question} {answer}")
        atom = Atom(
            prompt=question,
            answer=answer,
            embedding=embedding_to_bytes(vec),
            agent_id="agent_search",
        )
        store.write_atom(atom)
        print(f"  -> Wrote atom {atom.id[:8]}")
        print()

    stats = store.stats()
    print(f"Agent Search done. Store: {stats.total_atoms} atoms.")
    store.close()


if __name__ == "__main__":
    import tempfile

    db = os.path.join(tempfile.mkdtemp(), "shared.db")
    main(db)
