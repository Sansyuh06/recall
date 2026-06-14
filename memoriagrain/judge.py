"""Agreement judge for memoriagrain's three-gate promotion algorithm.

Determines whether a cluster of atoms share a common claim with
sufficiently low disagreement to warrant promotion to a pattern.

Two paths:
  - OpenAI: gpt-4o-mini produces {"common_claim": str, "disagreement": float}
  - Fallback: deterministic heuristic using difflib.SequenceMatcher
"""

from __future__ import annotations

import difflib
import json
import os
from itertools import combinations

from memoriagrain.store.base import Atom


def _openai_available() -> bool:
    """Check whether OpenAI API is available for judging."""
    return os.environ.get("OPENAI_API_KEY") is not None


def _judge_with_openai(atoms: list[Atom]) -> dict[str, object]:
    """Use gpt-4o-mini to judge agreement across a cluster of atoms.

    Sends the atom answers to the model and asks for a structured response
    with the common claim and a disagreement score.
    """
    from openai import OpenAI

    client = OpenAI()

    atom_texts = "\n---\n".join(f"Q: {a.prompt}\nA: {a.answer}" for a in atoms)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are analyzing a cluster of question-answer pairs for agreement. "
                    "Extract the common claim they share and rate the level of disagreement. "
                    'Respond with JSON: {"common_claim": "...", "disagreement": 0.0-1.0}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Analyze these {len(atoms)} related Q&A pairs:\n\n{atom_texts}\n\n"
                    "What is the common claim? How much do they disagree (0=total agreement, 1=total contradiction)?"
                ),
            },
        ],
        temperature=0.0,
        max_tokens=300,
    )

    content = response.choices[0].message.content or "{}"
    try:
        result = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return _judge_with_heuristic(atoms)

    return {
        "common_claim": str(result.get("common_claim", "")),
        "disagreement": float(result.get("disagreement", 1.0)),
    }


def _judge_with_heuristic(atoms: list[Atom]) -> dict[str, object]:
    """Deterministic fallback judge using SequenceMatcher.

    Computes pairwise text similarity across atom answers using
    difflib.SequenceMatcher. The common claim is the longest atom
    answer (as a proxy for the most detailed). Disagreement is
    1 - mean(pairwise_ratio).
    """
    answers = [a.answer for a in atoms]

    if len(answers) < 2:
        return {
            "common_claim": answers[0] if answers else "",
            "disagreement": 0.0,
        }

    # Compute pairwise similarity ratios
    ratios: list[float] = []
    for a, b in combinations(answers, 2):
        ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
        ratios.append(ratio)

    mean_ratio = sum(ratios) / len(ratios) if ratios else 0.0
    disagreement = 1.0 - mean_ratio

    # Use the longest answer as the common claim proxy, or build a
    # summary from the most frequently shared tokens
    common_claim = _extract_common_claim(answers)

    return {
        "common_claim": common_claim,
        "disagreement": round(disagreement, 4),
    }


def _extract_common_claim(answers: list[str]) -> str:
    """Extract a common claim from multiple answers.

    Uses token overlap to find the most representative answer.
    The answer with the highest average similarity to all others
    is chosen as the common claim.
    """
    if not answers:
        return ""
    if len(answers) == 1:
        return answers[0]

    best_answer = answers[0]
    best_score = 0.0

    for i, answer in enumerate(answers):
        total = 0.0
        for j, other in enumerate(answers):
            if i != j:
                total += difflib.SequenceMatcher(None, answer.lower(), other.lower()).ratio()
        avg = total / (len(answers) - 1)
        if avg > best_score:
            best_score = avg
            best_answer = answer

    return best_answer


def judge_cluster(atoms: list[Atom]) -> dict[str, object]:
    """Judge the agreement level of a cluster of atoms.

    This is the core function used by the promotion algorithm (Gate 2)
    and by the heal module for contradiction detection.

    When OPENAI_API_KEY is available, uses gpt-4o-mini for nuanced
    judgment. Otherwise falls back to a deterministic heuristic using
    difflib.SequenceMatcher so tests remain hermetic.

    Args:
        atoms: A list of atoms in the same embedding cluster.

    Returns:
        A dict with:
          - common_claim (str): The shared claim across the cluster.
          - disagreement (float): 0.0 (total agreement) to 1.0 (contradiction).
    """
    if not atoms:
        return {"common_claim": "", "disagreement": 1.0}

    if len(atoms) == 1:
        return {"common_claim": atoms[0].answer, "disagreement": 0.0}

    if _openai_available():
        return _judge_with_openai(atoms)

    return _judge_with_heuristic(atoms)
