"""Before: Naive agent without memoriagrain.

Answers 5 questions about Foundry IQ without any memory. Each question
is answered independently, with no knowledge carried between calls.

Uses the stub LLM if no OPENAI_API_KEY is set.
"""

from __future__ import annotations

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from examples.foundry_before_after.stub_llm import stub_complete

QUESTIONS = [
    "How does authentication work in Foundry IQ?",
    "What is a knowledge base in Foundry IQ?",
    "How do I search a knowledge base?",
    "How does authentication work in Foundry IQ?",  # repeated question
    "What are the best practices for agent memory?",
]


def main() -> None:
    """Run the naive agent without memoriagrain."""
    print("=" * 60)
    print("BEFORE: Agent without memoriagrain")
    print("=" * 60)
    print()

    total_tokens = 0
    total_latency = 0.0
    total_cost = 0.0

    for i, question in enumerate(QUESTIONS):
        print(f"Q{i + 1}: {question}")

        result = stub_complete(question, i)

        answer = str(result["answer"])
        tokens = int(result["tokens"])
        latency_ms = int(result["latency_ms"])
        cost = float(result["cost"])

        total_tokens += tokens
        total_latency += latency_ms
        total_cost += cost

        print(f"A{i + 1}: {answer[:120]}...")
        print(f"    [{tokens} tokens, {latency_ms}ms, ${cost:.4f}]")
        print()

    print("-" * 60)
    print(f"Total: {total_tokens} tokens, {total_latency:.0f}ms, ${total_cost:.4f}")
    print(f"Note: Q4 repeated Q1 but was answered from scratch.")
    print("=" * 60)


if __name__ == "__main__":
    main()
