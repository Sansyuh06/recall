"""Confidence scoring for memoriagrain memories.

Computes a composite confidence score in [0.0, 1.0] for any memory
based on three factors:

  1. Grain bonus: atoms get a lower base (0.5), patterns get 0.7,
     principles get 0.9 -- reflecting the promotion path they survived.

  2. Recency factor: memories recalled recently score higher.
     Decays exponentially with a 30-day half-life.

  3. Agreement factor: for patterns and principles, the stored
     confidence from the judge's agreement assessment.

Final score: grain_bonus * recency_factor * agreement_factor
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from memoriagrain.store.base import Memory

# Base confidence by grain level
GRAIN_BONUS = {
    "atom": 0.5,
    "pattern": 0.7,
    "principle": 0.9,
}

# Half-life for recency decay in days
RECENCY_HALF_LIFE_DAYS = 30.0


def confidence(memory: Memory) -> float:
    """Compute the composite confidence score for a memory.

    Args:
        memory: The memory to score.

    Returns:
        A float in [0.0, 1.0].
    """
    grain_bonus = GRAIN_BONUS.get(memory.grain, 0.5)
    recency_factor = _recency_factor(memory)
    agreement_factor = _agreement_factor(memory)

    score = grain_bonus * recency_factor * agreement_factor
    return round(min(1.0, max(0.0, score)), 4)


def _recency_factor(memory: Memory) -> float:
    """Compute recency factor based on last_recalled_at.

    Returns 1.0 for very recently recalled memories, decaying
    exponentially with a 30-day half-life.
    """
    if not memory.last_recalled_at:
        # Never recalled -- use written_at as a proxy
        if memory.written_at:
            try:
                written = datetime.fromisoformat(memory.written_at)
                age_days = (datetime.now(UTC) - written).total_seconds() / 86400.0
                return math.exp(-age_days * math.log(2) / RECENCY_HALF_LIFE_DAYS)
            except (ValueError, TypeError):
                pass
        return 0.5  # neutral default

    try:
        last_recalled = datetime.fromisoformat(memory.last_recalled_at)
        age_days = (datetime.now(UTC) - last_recalled).total_seconds() / 86400.0
        return math.exp(-age_days * math.log(2) / RECENCY_HALF_LIFE_DAYS)
    except (ValueError, TypeError):
        return 0.5


def _agreement_factor(memory: Memory) -> float:
    """Compute agreement factor from the stored confidence.

    For atoms (which have no agreement assessment), returns 1.0.
    For patterns and principles, uses the stored confidence directly.
    """
    if memory.grain == "atom":
        return 1.0

    # Stored confidence is already 1 - disagreement from the judge
    if memory.confidence > 0:
        return memory.confidence

    return 0.5  # neutral default for patterns/principles without a score
