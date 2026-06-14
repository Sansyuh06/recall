"""Three-gate promotion algorithm for memoriagrain.

Atoms become patterns (and patterns become principles) when all three
gates pass:

  GATE 1 -- Density
    N or more atoms with pairwise cosine similarity >= threshold
    form a cluster. Default N=5, threshold=0.82.

  GATE 2 -- Agreement
    A judge (gpt-4o-mini or deterministic fallback) reads the cluster
    and reports {common_claim, disagreement}. Promote only if
    disagreement < max_disagreement (default 0.2).

  GATE 3 -- Recency
    At least min_recent (default 2) of the cluster atoms must have
    last_recalled_at within the recency_window (default 30 days).

Config knob: memoriagrain config set promotion.strictness {loose|default|strict}
adjusts the thresholds for all three gates simultaneously.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from memoriagrain.embeddings import bytes_to_embedding, cosine_similarity, embed, embedding_to_bytes
from memoriagrain.judge import judge_cluster
from memoriagrain.store.base import Atom, Pattern, Principle, Store, _new_id


@dataclass
class PromotionConfig:
    """Threshold configuration for the three-gate algorithm."""

    min_cluster_size: int = 5
    similarity_threshold: float = 0.82
    max_disagreement: float = 0.2
    min_recent: int = 2
    recency_window_days: int = 30

    @classmethod
    def from_strictness(cls, strictness: str) -> PromotionConfig:
        """Create a config from a named strictness level.

        Args:
            strictness: One of 'loose', 'default', 'strict'.
        """
        configs = {
            "loose": cls(
                min_cluster_size=3,
                similarity_threshold=0.75,
                max_disagreement=0.3,
                min_recent=1,
                recency_window_days=60,
            ),
            "default": cls(),
            "strict": cls(
                min_cluster_size=7,
                similarity_threshold=0.88,
                max_disagreement=0.1,
                min_recent=3,
                recency_window_days=14,
            ),
        }
        return configs.get(strictness, cls())


class PromoteWorker:
    """Runs the three-gate promotion algorithm over the store.

    Call run_once() to perform a single promotion pass. Idempotent:
    atoms already promoted (promoted_into_pattern_id is set) are skipped.
    The same logic applies one layer up for pattern-to-principle promotion.
    """

    def __init__(
        self,
        store: Store,
        strictness: str = "default",
    ) -> None:
        """Initialize the promotion worker.

        Args:
            store: The storage backend to operate on.
            strictness: One of 'loose', 'default', 'strict'.
        """
        self.store = store
        self.config = PromotionConfig.from_strictness(strictness)

    def run_once(self) -> list[str]:
        """Execute a single promotion pass.

        Returns:
            List of newly created pattern/principle IDs.
        """
        created_ids: list[str] = []

        # Promote atoms -> patterns
        atom_patterns = self._promote_atoms_to_patterns()
        created_ids.extend(atom_patterns)

        # Promote patterns -> principles
        principle_ids = self._promote_patterns_to_principles()
        created_ids.extend(principle_ids)

        return created_ids

    def _promote_atoms_to_patterns(self) -> list[str]:
        """Find atom clusters and promote qualifying ones to patterns."""
        atoms = [
            a
            for a in self.store.all_atoms()
            if not a.promoted_into_pattern_id and not a.decayed and not a.superseded_by
        ]

        if len(atoms) < self.config.min_cluster_size:
            return []

        clusters = self._find_clusters(atoms)
        created: list[str] = []

        for cluster in clusters:
            pattern_id = self._try_promote_cluster(cluster, grain="atom")
            if pattern_id:
                created.append(pattern_id)

        return created

    def _promote_patterns_to_principles(self) -> list[str]:
        """Find pattern clusters and promote qualifying ones to principles."""
        patterns = [p for p in self.store.all_patterns() if not p.promoted_into_principle_id]

        if len(patterns) < self.config.min_cluster_size:
            return []

        # Convert patterns to atom-like objects for clustering
        pseudo_atoms = [
            Atom(
                id=p.id,
                prompt="",
                answer=p.text,
                embedding=p.embedding,
                written_at=p.written_at,
                last_recalled_at=p.last_recalled_at,
                recall_count=p.recall_count,
            )
            for p in patterns
        ]

        clusters = self._find_clusters(pseudo_atoms)
        created: list[str] = []

        for cluster in clusters:
            principle_id = self._try_promote_cluster(cluster, grain="pattern")
            if principle_id:
                created.append(principle_id)

        return created

    def _find_clusters(self, items: list[Atom]) -> list[list[Atom]]:
        """Find clusters of similar items using greedy cosine grouping.

        This is a simple greedy approach: for each unassigned item, find
        all items within the similarity threshold and form a cluster.
        Items can only belong to one cluster (first-match wins).
        """
        if not items:
            return []

        # Pre-compute embeddings
        embeddings: list[tuple[Atom, np.ndarray]] = []
        for item in items:
            if item.embedding:
                vec = bytes_to_embedding(item.embedding)
                embeddings.append((item, vec))

        if len(embeddings) < self.config.min_cluster_size:
            return []

        assigned: set[str] = set()
        clusters: list[list[Atom]] = []

        for i, (item_a, vec_a) in enumerate(embeddings):
            if item_a.id in assigned:
                continue

            cluster = [item_a]
            for j, (item_b, vec_b) in enumerate(embeddings):
                if i == j or item_b.id in assigned:
                    continue
                sim = cosine_similarity(vec_a, vec_b)
                if sim >= self.config.similarity_threshold:
                    cluster.append(item_b)

            if len(cluster) >= self.config.min_cluster_size:
                for c in cluster:
                    assigned.add(c.id)
                clusters.append(cluster)

        return clusters

    def _try_promote_cluster(self, cluster: list[Atom], grain: str) -> str | None:
        """Attempt to promote a cluster through all three gates.

        Args:
            cluster: The cluster of atoms (or pseudo-atoms for patterns).
            grain: 'atom' for atom->pattern, 'pattern' for pattern->principle.

        Returns:
            The new pattern/principle ID if promotion succeeds, else None.
        """
        # GATE 1: Density (already passed by virtue of cluster size)

        # GATE 2: Agreement
        judgment = judge_cluster(cluster)
        common_claim = str(judgment.get("common_claim", ""))
        disagreement = float(str(judgment.get("disagreement", 1.0)))

        if disagreement >= self.config.max_disagreement:
            return None

        # GATE 3: Recency
        cutoff = datetime.now(UTC) - timedelta(days=self.config.recency_window_days)
        recent_count = sum(
            1 for a in cluster if a.last_recalled_at and a.last_recalled_at >= cutoff
        )
        if recent_count < self.config.min_recent:
            return None

        # All three gates passed -- promote
        confidence = round(1.0 - disagreement, 4)
        claim_embedding = embed(common_claim)
        emb_bytes = embedding_to_bytes(claim_embedding)

        if grain == "atom":
            pattern = Pattern(
                id=_new_id(),
                text=common_claim,
                embedding=emb_bytes,
                derived_from=[a.id for a in cluster],
                confidence=confidence,
            )
            self.store.write_pattern(pattern)

            # Mark atoms as promoted
            for atom in cluster:
                atom.promoted_into_pattern_id = pattern.id
                self.store.update_atom(atom)

            return pattern.id

        else:  # pattern -> principle
            principle = Principle(
                id=_new_id(),
                text=common_claim,
                embedding=emb_bytes,
                derived_from=[a.id for a in cluster],
                confidence=confidence,
            )
            self.store.write_principle(principle)

            # Mark patterns as promoted
            for pseudo_atom in cluster:
                p = self.store.get_pattern(pseudo_atom.id)
                if p:
                    p.promoted_into_principle_id = principle.id
                    self.store.update_pattern(p)

            return principle.id
