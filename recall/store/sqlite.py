"""SQLite storage backend for recall.

This is the offline-safe fallback store used by all demos and tests.
Schema stores atoms, patterns, and principles with BLOB-encoded numpy
embedding vectors. Cosine similarity search is done in Python over
deserialized vectors (no FAISS dependency in v0.1).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from recall.embeddings import bytes_to_embedding, cosine_similarity
from recall.store.base import (
    Atom,
    Memory,
    Pattern,
    Principle,
    Store,
    StoreStats,
    _new_id,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS atoms (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    embedding BLOB,
    agent_id TEXT DEFAULT 'default',
    written_at TEXT NOT NULL,
    last_recalled_at TEXT,
    recall_count INTEGER DEFAULT 0,
    source_doc TEXT,
    source_mtime REAL,
    promoted_into_pattern_id TEXT,
    superseded_by TEXT,
    decayed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS patterns (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    embedding BLOB,
    derived_from TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    written_at TEXT NOT NULL,
    last_recalled_at TEXT,
    recall_count INTEGER DEFAULT 0,
    promoted_into_principle_id TEXT
);

CREATE TABLE IF NOT EXISTS principles (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    embedding BLOB,
    derived_from TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    written_at TEXT NOT NULL,
    last_recalled_at TEXT,
    recall_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _dt_to_str(dt: datetime | None) -> str | None:
    """Convert datetime to ISO 8601 string."""
    if dt is None:
        return None
    return dt.isoformat()


def _str_to_dt(s: str | None) -> datetime | None:
    """Parse an ISO 8601 string to datetime."""
    if s is None:
        return None
    return datetime.fromisoformat(s)


class SQLiteStore(Store):
    """Concrete Store implementation backed by a local SQLite database.

    The database file is created on first use. All embedding-based search
    is performed by deserializing numpy vectors from BLOBs and computing
    cosine similarity in Python. This avoids external dependencies like
    FAISS for v0.1 while remaining correct.
    """

    def __init__(self, db_path: str | Path = ".recall/recall.db") -> None:
        """Initialize the SQLite store.

        Args:
            db_path: Path to the SQLite database file.
                     Created if it does not exist.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def write_atom(self, atom: Atom) -> str:
        """Persist an atom and return its ID."""
        if not atom.id:
            atom.id = _new_id()
        self._conn.execute(
            """INSERT OR REPLACE INTO atoms
               (id, prompt, answer, embedding, agent_id, written_at,
                last_recalled_at, recall_count, source_doc, source_mtime,
                promoted_into_pattern_id, superseded_by, decayed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                atom.id,
                atom.prompt,
                atom.answer,
                atom.embedding,
                atom.agent_id,
                _dt_to_str(atom.written_at),
                _dt_to_str(atom.last_recalled_at),
                atom.recall_count,
                atom.source_doc,
                atom.source_mtime,
                atom.promoted_into_pattern_id,
                atom.superseded_by,
                int(atom.decayed),
            ),
        )
        self._conn.commit()
        return atom.id

    def write_pattern(self, pattern: Pattern) -> str:
        """Persist a pattern and return its ID."""
        if not pattern.id:
            pattern.id = _new_id()
        self._conn.execute(
            """INSERT OR REPLACE INTO patterns
               (id, text, embedding, derived_from, confidence, written_at,
                last_recalled_at, recall_count, promoted_into_principle_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pattern.id,
                pattern.text,
                pattern.embedding,
                json.dumps(pattern.derived_from),
                pattern.confidence,
                _dt_to_str(pattern.written_at),
                _dt_to_str(pattern.last_recalled_at),
                pattern.recall_count,
                pattern.promoted_into_principle_id,
            ),
        )
        self._conn.commit()
        return pattern.id

    def write_principle(self, principle: Principle) -> str:
        """Persist a principle and return its ID."""
        if not principle.id:
            principle.id = _new_id()
        self._conn.execute(
            """INSERT OR REPLACE INTO principles
               (id, text, embedding, derived_from, confidence, written_at,
                last_recalled_at, recall_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                principle.id,
                principle.text,
                principle.embedding,
                json.dumps(principle.derived_from),
                principle.confidence,
                _dt_to_str(principle.written_at),
                _dt_to_str(principle.last_recalled_at),
                principle.recall_count,
            ),
        )
        self._conn.commit()
        return principle.id

    def search(self, query_embedding: bytes, grain: str, k: int = 5) -> list[Memory]:
        """Find the k most similar memories by cosine similarity.

        For grain="auto", searches principles first, then patterns, then atoms,
        returning the first non-empty result set.
        """
        if grain == "auto":
            for g in ("principle", "pattern", "atom"):
                results = self._search_grain(query_embedding, g, k)
                if results:
                    return results
            return []
        return self._search_grain(query_embedding, grain, k)

    def _search_grain(self, query_embedding: bytes, grain: str, k: int) -> list[Memory]:
        """Search a single grain level by cosine similarity."""
        query_vec = bytes_to_embedding(query_embedding)
        table = {"atom": "atoms", "pattern": "patterns", "principle": "principles"}[grain]

        if grain == "atom":
            rows = self._conn.execute(
                """SELECT id, prompt, answer, embedding, agent_id, written_at,
                          last_recalled_at, recall_count, source_doc, decayed,
                          superseded_by
                   FROM atoms WHERE decayed = 0 AND superseded_by IS NULL"""
            ).fetchall()
        elif grain == "pattern":
            rows = self._conn.execute(
                """SELECT id, text, embedding, derived_from, confidence, written_at,
                          last_recalled_at, recall_count
                   FROM patterns"""
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT id, text, embedding, derived_from, confidence, written_at,
                          last_recalled_at, recall_count
                   FROM principles"""
            ).fetchall()

        scored: list[tuple[float, Memory]] = []
        for row in rows:
            emb_data = row["embedding"]
            if not emb_data:
                continue
            row_vec = bytes_to_embedding(emb_data)
            if len(row_vec) != len(query_vec):
                continue
            sim = cosine_similarity(query_vec, row_vec)

            if grain == "atom":
                memory_text = f"Q: {row['prompt']}\nA: {row['answer']}"
                derived = []
                confidence = 0.5  # base atom confidence
                source_doc = row["source_doc"]
                agent_id = row["agent_id"]
            else:
                memory_text = row["text"]
                derived = json.loads(row["derived_from"])
                confidence = row["confidence"]
                source_doc = None
                agent_id = "default"

            mem = Memory(
                memory=memory_text,
                grain=grain,
                confidence=confidence,
                freshness="unknown",
                derived_from=derived,
                written_at=row["written_at"] or "",
                last_recalled_at=row["last_recalled_at"],
                source_doc=source_doc,
                agent_id=agent_id,
                id=row["id"],
            )
            scored.append((sim, mem))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = [mem for _, mem in scored[:k]]

        # Update last_recalled_at and recall_count for returned memories
        now_str = _dt_to_str(datetime.now(UTC))
        for mem in results:
            self._conn.execute(
                f"UPDATE {table} SET last_recalled_at = ?, recall_count = recall_count + 1 WHERE id = ?",
                (now_str, mem.id),
            )
        self._conn.commit()

        return results

    def get(self, memory_id: str) -> Memory | None:
        """Retrieve a single memory by ID from any grain level."""
        # Check atoms
        row = self._conn.execute("SELECT * FROM atoms WHERE id = ?", (memory_id,)).fetchone()
        if row:
            return Memory(
                memory=f"Q: {row['prompt']}\nA: {row['answer']}",
                grain="atom",
                confidence=0.5,
                freshness="unknown",
                derived_from=[],
                written_at=row["written_at"] or "",
                last_recalled_at=row["last_recalled_at"],
                source_doc=row["source_doc"],
                agent_id=row["agent_id"],
                id=row["id"],
            )

        # Check patterns
        row = self._conn.execute("SELECT * FROM patterns WHERE id = ?", (memory_id,)).fetchone()
        if row:
            return Memory(
                memory=row["text"],
                grain="pattern",
                confidence=row["confidence"],
                freshness="unknown",
                derived_from=json.loads(row["derived_from"]),
                written_at=row["written_at"] or "",
                last_recalled_at=row["last_recalled_at"],
                id=row["id"],
            )

        # Check principles
        row = self._conn.execute("SELECT * FROM principles WHERE id = ?", (memory_id,)).fetchone()
        if row:
            return Memory(
                memory=row["text"],
                grain="principle",
                confidence=row["confidence"],
                freshness="unknown",
                derived_from=json.loads(row["derived_from"]),
                written_at=row["written_at"] or "",
                last_recalled_at=row["last_recalled_at"],
                id=row["id"],
            )

        return None

    def get_atom(self, atom_id: str) -> Atom | None:
        """Retrieve a single atom by ID."""
        row = self._conn.execute("SELECT * FROM atoms WHERE id = ?", (atom_id,)).fetchone()
        if not row:
            return None
        return self._row_to_atom(row)

    def get_pattern(self, pattern_id: str) -> Pattern | None:
        """Retrieve a single pattern by ID."""
        row = self._conn.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
        if not row:
            return None
        return Pattern(
            id=row["id"],
            text=row["text"],
            embedding=row["embedding"] or b"",
            derived_from=json.loads(row["derived_from"]),
            confidence=row["confidence"],
            written_at=_str_to_dt(row["written_at"]) or datetime.now(UTC),
            last_recalled_at=_str_to_dt(row["last_recalled_at"]),
            recall_count=row["recall_count"],
            promoted_into_principle_id=row["promoted_into_principle_id"],
        )

    def all_atoms(self, since: datetime | None = None) -> Iterator[Atom]:
        """Iterate over all atoms, optionally filtered by write time."""
        if since:
            rows = self._conn.execute(
                "SELECT * FROM atoms WHERE written_at >= ? ORDER BY written_at",
                (_dt_to_str(since),),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM atoms ORDER BY written_at").fetchall()

        for row in rows:
            yield self._row_to_atom(row)

    def all_patterns(self, since: datetime | None = None) -> Iterator[Pattern]:
        """Iterate over all patterns, optionally filtered by write time."""
        if since:
            rows = self._conn.execute(
                "SELECT * FROM patterns WHERE written_at >= ? ORDER BY written_at",
                (_dt_to_str(since),),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM patterns ORDER BY written_at").fetchall()

        for row in rows:
            yield Pattern(
                id=row["id"],
                text=row["text"],
                embedding=row["embedding"] or b"",
                derived_from=json.loads(row["derived_from"]),
                confidence=row["confidence"],
                written_at=_str_to_dt(row["written_at"]) or datetime.now(UTC),
                last_recalled_at=_str_to_dt(row["last_recalled_at"]),
                recall_count=row["recall_count"],
                promoted_into_principle_id=row["promoted_into_principle_id"],
            )

    def all_principles(self) -> Iterator[Principle]:
        """Iterate over all principles."""
        rows = self._conn.execute("SELECT * FROM principles ORDER BY written_at").fetchall()
        for row in rows:
            yield Principle(
                id=row["id"],
                text=row["text"],
                embedding=row["embedding"] or b"",
                derived_from=json.loads(row["derived_from"]),
                confidence=row["confidence"],
                written_at=_str_to_dt(row["written_at"]) or datetime.now(UTC),
                last_recalled_at=_str_to_dt(row["last_recalled_at"]),
                recall_count=row["recall_count"],
            )

    def update_atom(self, atom: Atom) -> None:
        """Update an existing atom in place."""
        self._conn.execute(
            """UPDATE atoms SET
               prompt = ?, answer = ?, embedding = ?, agent_id = ?,
               written_at = ?, last_recalled_at = ?, recall_count = ?,
               source_doc = ?, source_mtime = ?, promoted_into_pattern_id = ?,
               superseded_by = ?, decayed = ?
               WHERE id = ?""",
            (
                atom.prompt,
                atom.answer,
                atom.embedding,
                atom.agent_id,
                _dt_to_str(atom.written_at),
                _dt_to_str(atom.last_recalled_at),
                atom.recall_count,
                atom.source_doc,
                atom.source_mtime,
                atom.promoted_into_pattern_id,
                atom.superseded_by,
                int(atom.decayed),
                atom.id,
            ),
        )
        self._conn.commit()

    def update_pattern(self, pattern: Pattern) -> None:
        """Update an existing pattern in place."""
        self._conn.execute(
            """UPDATE patterns SET
               text = ?, embedding = ?, derived_from = ?, confidence = ?,
               written_at = ?, last_recalled_at = ?, recall_count = ?,
               promoted_into_principle_id = ?
               WHERE id = ?""",
            (
                pattern.text,
                pattern.embedding,
                json.dumps(pattern.derived_from),
                pattern.confidence,
                _dt_to_str(pattern.written_at),
                _dt_to_str(pattern.last_recalled_at),
                pattern.recall_count,
                pattern.promoted_into_principle_id,
                pattern.id,
            ),
        )
        self._conn.commit()

    def delete(self, memory_id: str) -> None:
        """Remove a memory by ID from any grain level."""
        for table in ("atoms", "patterns", "principles"):
            self._conn.execute(f"DELETE FROM {table} WHERE id = ?", (memory_id,))
        self._conn.commit()

    def stats(self) -> StoreStats:
        """Compute and return aggregate store statistics."""
        total_atoms = self._conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0]
        total_patterns = self._conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
        total_principles = self._conn.execute("SELECT COUNT(*) FROM principles").fetchone()[0]
        decayed = self._conn.execute("SELECT COUNT(*) FROM atoms WHERE decayed = 1").fetchone()[0]

        agents_rows = self._conn.execute("SELECT DISTINCT agent_id FROM atoms").fetchall()
        agents = [r[0] for r in agents_rows]

        oldest_row = self._conn.execute("SELECT MIN(written_at) FROM atoms").fetchone()
        newest_row = self._conn.execute("SELECT MAX(written_at) FROM atoms").fetchone()

        return StoreStats(
            total_atoms=total_atoms,
            total_patterns=total_patterns,
            total_principles=total_principles,
            decayed_atoms=decayed,
            fresh_atoms=total_atoms - decayed,
            stale_atoms=0,  # computed by freshness checker
            agents=agents,
            oldest_memory=oldest_row[0] if oldest_row else None,
            newest_memory=newest_row[0] if newest_row else None,
        )

    def get_config(self, key: str, default: str = "") -> str:
        """Read a config value from the meta table."""
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_config(self, key: str, value: str) -> None:
        """Write a config value to the meta table."""
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def _row_to_atom(self, row: sqlite3.Row) -> Atom:
        """Convert a database row to an Atom dataclass."""
        return Atom(
            id=row["id"],
            prompt=row["prompt"],
            answer=row["answer"],
            embedding=row["embedding"] or b"",
            agent_id=row["agent_id"],
            written_at=_str_to_dt(row["written_at"]) or datetime.now(UTC),
            last_recalled_at=_str_to_dt(row["last_recalled_at"]),
            recall_count=row["recall_count"],
            source_doc=row["source_doc"],
            source_mtime=row["source_mtime"],
            promoted_into_pattern_id=row["promoted_into_pattern_id"],
            superseded_by=row["superseded_by"],
            decayed=bool(row["decayed"]),
        )
