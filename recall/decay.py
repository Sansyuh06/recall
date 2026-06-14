"""Exponential decay worker for recall memory management.

Atoms whose effective weight falls below a threshold are marked as
decayed. Decayed atoms are excluded from search results but kept in
the database for provenance integrity (patterns derived from them
still reference their IDs).

The effective weight formula:
  weight = recall_count * exp(-age_days / half_life_days)

Default half-life: 30 days.
Default decay threshold: 0.05.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from recall.store.base import Atom, Store


def effective_weight(atom: Atom, half_life_days: float = 30.0) -> float:
    """Compute the effective weight of an atom based on decay.

    Args:
        atom: The atom to evaluate.
        half_life_days: The half-life in days for exponential decay.

    Returns:
        The effective weight (recall_count * exp(-age/half_life)).
        Returns 0.0 for atoms that have never been recalled.
    """
    # Never recalled -- use a small base weight so new atoms don't immediately decay
    base = 0.5 if atom.recall_count == 0 else float(atom.recall_count)

    age = datetime.now(UTC) - atom.written_at
    age_days = age.total_seconds() / 86400.0

    decay_factor = math.exp(-age_days * math.log(2) / half_life_days)
    return base * decay_factor


class DecayWorker:
    """Marks atoms as decayed when their effective weight drops below threshold.

    Decayed atoms remain in the database for provenance but are excluded
    from search results.
    """

    def __init__(
        self,
        store: Store,
        half_life_days: float = 30.0,
        threshold: float = 0.05,
    ) -> None:
        """Initialize the decay worker.

        Args:
            store: The storage backend.
            half_life_days: Exponential decay half-life in days.
            threshold: Weight below which an atom is marked decayed.
        """
        self.store = store
        self.half_life_days = half_life_days
        self.threshold = threshold

    def run_once(self) -> int:
        """Perform a single decay pass over all atoms.

        Returns:
            The number of atoms newly marked as decayed.
        """
        decayed_count = 0

        for atom in self.store.all_atoms():
            if atom.decayed:
                continue

            weight = effective_weight(atom, self.half_life_days)
            if weight < self.threshold:
                atom.decayed = True
                self.store.update_atom(atom)
                decayed_count += 1

        return decayed_count
