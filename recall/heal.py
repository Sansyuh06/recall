"""Active contradiction resolver for recall.

Detects contradictions in the memory store and resolves them by:
1. Finding atom clusters with high disagreement (>= 0.2)
2. Picking a winner using confidence x recency
3. Tagging losers as superseded (kept for provenance, excluded from search)
4. Writing resolution details to .recall/heal.log

The heal command runs a promotion pass first, then contradiction resolution.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from recall.embeddings import bytes_to_embedding, cosine_similarity
from recall.judge import judge_cluster
from recall.promote import PromoteWorker
from recall.store.base import Atom, Store

logger = logging.getLogger(__name__)


@dataclass
class HealResolution:
    """Record of a single contradiction resolution."""

    winner_id: str
    loser_ids: list[str]
    reason: str
    disagreement: float
    resolved_at: str  # ISO 8601


class HealWorker:
    """Actively resolves contradictions in the memory store.

    Scans for atom clusters that disagree (judge disagreement >= threshold),
    then picks a winner based on confidence and recency, superseding the
    losers.
    """

    def __init__(
        self,
        store: Store,
        similarity_threshold: float = 0.82,
        disagreement_threshold: float = 0.2,
        log_path: Path | None = None,
    ) -> None:
        """Initialize the heal worker.

        Args:
            store: The storage backend.
            similarity_threshold: Cosine similarity for clustering.
            disagreement_threshold: Judge disagreement level that triggers resolution.
            log_path: Path to the heal log file. Defaults to .recall/heal.log.
        """
        self.store = store
        self.similarity_threshold = similarity_threshold
        self.disagreement_threshold = disagreement_threshold
        self.log_path = log_path or Path(".recall") / "heal.log"

    def run(self, dry_run: bool = False) -> list[HealResolution]:
        """Run the full heal pipeline.

        1. Run a promotion pass (PromoteWorker.run_once)
        2. Find contradicting clusters
        3. Resolve each contradiction

        Args:
            dry_run: If True, detect contradictions but do not apply resolutions.

        Returns:
            List of resolutions applied (or that would be applied in dry_run mode).
        """
        # Step 1: Run promotion first
        promoter = PromoteWorker(self.store)
        promoter.run_once()

        # Step 2: Find contradictions
        contradictions = self._find_contradictions()

        # Step 3: Resolve
        resolutions: list[HealResolution] = []
        for cluster, judgment in contradictions:
            resolution = self._resolve(cluster, judgment, dry_run=dry_run)
            if resolution:
                resolutions.append(resolution)

        # Step 4: Write log
        if resolutions:
            self._write_log(resolutions, dry_run=dry_run)

        return resolutions

    def _find_contradictions(
        self,
    ) -> list[tuple[list[Atom], dict[str, object]]]:
        """Find clusters of atoms with disagreement above threshold."""
        atoms = [a for a in self.store.all_atoms() if not a.decayed and not a.superseded_by]

        if len(atoms) < 2:
            return []

        # Build clusters using cosine similarity
        embeddings: list[tuple[Atom, np.ndarray]] = []
        for atom in atoms:
            if atom.embedding:
                vec = bytes_to_embedding(atom.embedding)
                embeddings.append((atom, vec))

        assigned: set[str] = set()
        contradictions: list[tuple[list[Atom], dict[str, object]]] = []

        for i, (atom_a, vec_a) in enumerate(embeddings):
            if atom_a.id in assigned:
                continue

            cluster = [atom_a]
            for j, (atom_b, vec_b) in enumerate(embeddings):
                if i == j or atom_b.id in assigned:
                    continue
                sim = cosine_similarity(vec_a, vec_b)
                if sim >= self.similarity_threshold:
                    cluster.append(atom_b)

            if len(cluster) >= 2:
                judgment = judge_cluster(cluster)
                disagreement = float(str(judgment.get("disagreement", 0.0)))
                if disagreement >= self.disagreement_threshold:
                    for a in cluster:
                        assigned.add(a.id)
                    contradictions.append((cluster, judgment))

        return contradictions

    def _resolve(
        self,
        cluster: list[Atom],
        judgment: dict[str, object],
        dry_run: bool = False,
    ) -> HealResolution | None:
        """Resolve a contradiction by picking a winner.

        Winner selection: highest (confidence_proxy * recency_factor).
        confidence_proxy for atoms is based on recall_count.
        recency_factor prefers recently recalled atoms.
        """
        if not cluster:
            return None

        now = datetime.now(UTC)
        best_atom = cluster[0]
        best_score = 0.0

        for atom in cluster:
            # Confidence proxy from recall count
            conf = min(1.0, atom.recall_count / 10.0) if atom.recall_count > 0 else 0.1

            # Recency factor: higher if recalled recently
            if atom.last_recalled_at:
                age_days = (now - atom.last_recalled_at).total_seconds() / 86400.0
                recency = 1.0 / (1.0 + age_days / 30.0)
            else:
                recency = 0.1

            score = conf * recency
            if score > best_score:
                best_score = score
                best_atom = atom

        loser_ids = [a.id for a in cluster if a.id != best_atom.id]

        if not dry_run:
            for atom in cluster:
                if atom.id != best_atom.id:
                    atom.superseded_by = best_atom.id
                    self.store.update_atom(atom)

        disagreement = float(str(judgment.get("disagreement", 0.0)))
        return HealResolution(
            winner_id=best_atom.id,
            loser_ids=loser_ids,
            reason=f"Winner selected by confidence*recency score ({best_score:.4f}). "
            f"Cluster disagreement: {disagreement:.4f}.",
            disagreement=disagreement,
            resolved_at=now.isoformat(),
        )

    def _write_log(self, resolutions: list[HealResolution], dry_run: bool = False) -> None:
        """Append resolution records to the heal log file."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        mode_label = "[DRY RUN] " if dry_run else ""

        with open(self.log_path, "a", encoding="utf-8") as f:
            for res in resolutions:
                entry = {
                    "mode": "dry_run" if dry_run else "applied",
                    "winner_id": res.winner_id,
                    "loser_ids": res.loser_ids,
                    "reason": res.reason,
                    "disagreement": res.disagreement,
                    "resolved_at": res.resolved_at,
                }
                f.write(f"{mode_label}{json.dumps(entry)}\n")

        logger.info(
            "Wrote %d %sresolutions to %s",
            len(resolutions),
            mode_label,
            self.log_path,
        )
