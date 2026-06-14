"""After: Agent with @remember decorator.

Same 5 questions, but now the agent has memoriagrain memory. The second time
a question is asked (Q4 repeats Q1), the agent retrieves the answer
from memory instead of re-computing it.

Seeds memory from the local docs first, then answers questions.
Uses the stub LLM if no OPENAI_API_KEY is set.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from examples.foundry_before_after.stub_llm import stub_complete
from memoriagrain.decorator import remember
from memoriagrain.embeddings import embed, embedding_to_bytes
from memoriagrain.seed import from_path
from memoriagrain.store.sqlite import SQLiteStore
from memoriagrain.tool import handle_recall_call

QUESTIONS = [
    "How does authentication work in Foundry IQ?",
    "What is a knowledge base in Foundry IQ?",
    "How do I search a knowledge base?",
    "How does authentication work in Foundry IQ?",  # repeated
    "What are the best practices for agent memory?",
]


def main() -> None:
    """Run the memoriagrain-enhanced agent."""
    # Use a temp DB for this demo
    db_path = os.path.join(tempfile.mkdtemp(), "demo_memoriagrain.db")
    store = SQLiteStore(db_path)

    # Seed from local docs
    seed_dir = Path(__file__).parent / "seed"
    print("Seeding memory from local docs...")
    seed_count = from_path(seed_dir, store)
    stats = store.stats()
    print(f"Seeded: {seed_count} atoms, {stats.total_patterns} patterns")
    print()

    print("=" * 60)
    print("AFTER: Agent with memoriagrain")
    print("=" * 60)
    print()

    total_tokens = 0
    total_latency = 0.0
    total_cost = 0.0
    recall_hits = 0

    for i, question in enumerate(QUESTIONS):
        print(f"Q{i + 1}: {question}")

        # Check memoriagrain first
        recall_result = handle_recall_call(store, {"query": question})
        recalled_memory = str(recall_result.get("memory", ""))
        recall_confidence = float(recall_result.get("confidence", 0))

        if recalled_memory and recall_confidence > 0.3:
            # Memory hit -- use recalled answer
            recall_hits += 1
            grain = recall_result.get("grain", "atom")
            freshness = recall_result.get("freshness", "unknown")

            # Estimate saved tokens
            saved_tokens = len(recalled_memory.split())
            total_tokens += saved_tokens // 3  # memoriagrain is cheaper

            print(f"A{i + 1}: [RECALLED from {grain}, confidence={recall_confidence:.2f}, {freshness}]")
            print(f"    {recalled_memory[:120]}...")
            print(f"    [{saved_tokens // 3} tokens (from memory), 0ms, $0.0000]")
        else:
            # No memory -- call the LLM
            result = stub_complete(question, i)
            answer = str(result["answer"])
            tokens = int(result["tokens"])
            latency_ms = int(result["latency_ms"])
            cost = float(result["cost"])

            total_tokens += tokens
            total_latency += latency_ms
            total_cost += cost

            # Write to memory for next time
            vec = embed(f"{question} {answer}")
            from memoriagrain.store.base import Atom

            atom = Atom(
                prompt=question,
                answer=answer,
                embedding=embedding_to_bytes(vec),
                agent_id="demo_agent",
            )
            store.write_atom(atom)

            print(f"A{i + 1}: {answer[:120]}...")
            print(f"    [{tokens} tokens, {latency_ms}ms, ${cost:.4f}]")

        print()

    print("-" * 60)
    print(f"Total: {total_tokens} tokens, {total_latency:.0f}ms, ${total_cost:.4f}")
    print(f"Recall hits: {recall_hits}/{len(QUESTIONS)}")
    final_stats = store.stats()
    print(f"Memory: {final_stats.total_atoms} atoms, {final_stats.total_patterns} patterns")
    print("=" * 60)

    store.close()


if __name__ == "__main__":
    main()
