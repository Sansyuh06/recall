"""Stub LLM for running examples without an API key.

Reads from a fixture file of canned Q&A pairs and returns deterministic
responses. Counts tokens by word splitting and reports fixed latency.

Honest about what it is: "captured against the stub LLM; real LLM
numbers will vary."
"""

from __future__ import annotations

import json
import time
from pathlib import Path

# Fixed latency table (seconds per question, simulating API round trips)
LATENCY_TABLE = [0.8, 1.2, 0.9, 1.5, 1.1]

# Load fixture Q&A pairs
_FIXTURES_PATH = Path(__file__).parent / "seed" / "qa_fixtures.json"
_fixtures: dict[str, str] | None = None


def _load_fixtures() -> dict[str, str]:
    global _fixtures
    if _fixtures is None:
        if _FIXTURES_PATH.exists():
            _fixtures = json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))
        else:
            _fixtures = {}
    return _fixtures


def stub_complete(prompt: str, question_index: int = 0) -> dict[str, object]:
    """Simulate an LLM completion with fixture data.

    Args:
        prompt: The question to answer.
        question_index: Index for latency table lookup.

    Returns:
        Dict with: answer, tokens, latency_ms, cost
    """
    fixtures = _load_fixtures()

    # Find best matching fixture
    answer = ""
    for key, value in fixtures.items():
        if key.lower() in prompt.lower() or prompt.lower() in key.lower():
            answer = value
            break

    if not answer:
        # Generic fallback
        answer = (
            f"Based on my knowledge, regarding '{prompt[:50]}': "
            "This topic requires further investigation. The available "
            "documentation suggests multiple approaches depending on "
            "the specific use case and deployment environment."
        )

    # Simulate latency
    latency = LATENCY_TABLE[question_index % len(LATENCY_TABLE)]
    time.sleep(latency)

    # Count tokens by word splitting
    prompt_tokens = len(prompt.split())
    answer_tokens = len(answer.split())
    total_tokens = prompt_tokens + answer_tokens

    # Approximate cost ($0.01 per 1K tokens)
    cost = total_tokens / 1000 * 0.01

    return {
        "answer": answer,
        "tokens": total_tokens,
        "latency_ms": int(latency * 1000),
        "cost": round(cost, 4),
    }
