"""Abstract base class for recall storage backends and shared data models.

All concrete backends (SQLite, Foundry IQ) implement the Store ABC.
Data flows through three grain levels: Atom -> Pattern -> Principle.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def _new_id() -> str:
    """Generate a new unique memory ID."""
    return uuid.uuid4().hex[:16]


@dataclass
class Atom:
    """The smallest unit of memory: a single question-answer observation.

    Atoms are created from agent interactions, seeded documents, or manual
    insertion. They carry embedding vectors for similarity search and
    provenance metadata for freshness tracking.
    """

    id: str = field(default_factory=_new_id)
    prompt: str = ""
    answer: str = ""
    embedding: bytes = b""
    agent_id: str = "default"
    written_at: datetime = field(default_factory=_now)
    last_recalled_at: datetime | None = None
    recall_count: int = 0
    source_doc: str | None = None
    source_mtime: float | None = None
    promoted_into_pattern_id: str | None = None
    superseded_by: str | None = None
    decayed: bool = False


@dataclass
class Pattern:
    """A consolidated claim derived from multiple agreeing atoms.

    Patterns are created by the three-gate promotion algorithm when a
    cluster of atoms passes density, agreement, and recency gates.
    """

    id: str = field(default_factory=_new_id)
    text: str = ""
    embedding: bytes = b""
    derived_from: list[str] = field(default_factory=list)
    confidence: float = 0.0
    written_at: datetime = field(default_factory=_now)
    last_recalled_at: datetime | None = None
    recall_count: int = 0
    promoted_into_principle_id: str | None = None


@dataclass
class Principle:
    """A high-confidence generalization derived from multiple patterns.

    Principles sit at the top of the grain hierarchy and represent the
    most consolidated, trustworthy knowledge in the store.
    """

    id: str = field(default_factory=_new_id)
    text: str = ""
    embedding: bytes = b""
    derived_from: list[str] = field(default_factory=list)
    confidence: float = 0.0
    written_at: datetime = field(default_factory=_now)
    last_recalled_at: datetime | None = None
    recall_count: int = 0


@dataclass
class Memory:
    """Unified recall response returned to the calling agent.

    Wraps any grain level with provenance, confidence, and freshness
    metadata so the agent can make informed decisions about trust.
    """

    memory: str
    grain: str  # "atom" | "pattern" | "principle"
    confidence: float
    freshness: str  # "fresh" | "stale" | "unknown"
    derived_from: list[str]
    written_at: str  # ISO 8601
    last_recalled_at: str | None
    source_doc: str | None = None
    truncated_at: str | None = None
    agent_id: str = "default"
    id: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serialize to the response dict shape defined in the API spec."""
        return {
            "memory": self.memory,
            "grain": self.grain,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "derived_from": self.derived_from,
            "written_at": self.written_at,
            "last_recalled_at": self.last_recalled_at,
            "source_doc": self.source_doc,
            "truncated_at": self.truncated_at,
        }


@dataclass
class StoreStats:
    """Aggregate statistics about the memory store."""

    total_atoms: int = 0
    total_patterns: int = 0
    total_principles: int = 0
    decayed_atoms: int = 0
    fresh_atoms: int = 0
    stale_atoms: int = 0
    agents: list[str] = field(default_factory=list)
    oldest_memory: str | None = None
    newest_memory: str | None = None


class Store(ABC):
    """Abstract base class for recall storage backends.

    Implementations must handle persistence, embedding-based search,
    and lifecycle management for all three grain levels.
    """

    @abstractmethod
    def write_atom(self, atom: Atom) -> str:
        """Persist an atom and return its ID."""
        ...

    @abstractmethod
    def write_pattern(self, pattern: Pattern) -> str:
        """Persist a pattern and return its ID."""
        ...

    @abstractmethod
    def write_principle(self, principle: Principle) -> str:
        """Persist a principle and return its ID."""
        ...

    @abstractmethod
    def search(self, query_embedding: bytes, grain: str, k: int = 5) -> list[Memory]:
        """Find the k most similar memories at the given grain level.

        Args:
            query_embedding: The embedding vector of the query as bytes.
            grain: One of "atom", "pattern", "principle", or "auto".
            k: Maximum number of results.

        Returns:
            List of Memory objects sorted by similarity descending.
        """
        ...

    @abstractmethod
    def get(self, memory_id: str) -> Memory | None:
        """Retrieve a single memory by ID, or None if not found."""
        ...

    @abstractmethod
    def get_atom(self, atom_id: str) -> Atom | None:
        """Retrieve a single atom by ID, or None if not found."""
        ...

    @abstractmethod
    def get_pattern(self, pattern_id: str) -> Pattern | None:
        """Retrieve a single pattern by ID, or None if not found."""
        ...

    @abstractmethod
    def all_atoms(self, since: datetime | None = None) -> Iterator[Atom]:
        """Iterate over all atoms, optionally filtered by write time."""
        ...

    @abstractmethod
    def all_patterns(self, since: datetime | None = None) -> Iterator[Pattern]:
        """Iterate over all patterns, optionally filtered by write time."""
        ...

    @abstractmethod
    def all_principles(self) -> Iterator[Principle]:
        """Iterate over all principles."""
        ...

    @abstractmethod
    def update_atom(self, atom: Atom) -> None:
        """Update an existing atom in place."""
        ...

    @abstractmethod
    def update_pattern(self, pattern: Pattern) -> None:
        """Update an existing pattern in place."""
        ...

    @abstractmethod
    def delete(self, memory_id: str) -> None:
        """Remove a memory by ID."""
        ...

    @abstractmethod
    def stats(self) -> StoreStats:
        """Compute and return aggregate store statistics."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by the store."""
        ...
