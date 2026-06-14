"""Foundry IQ knowledge base storage backend for recall.

Implements the Store interface using Microsoft Foundry IQ's REST API
as the persistence layer. This is the primary backend for enterprise
deployments where agents share a Foundry IQ knowledge base.

Authentication uses DefaultAzureCredential from azure-identity.

Required environment variables:
    FOUNDRY_IQ_PROJECT: The Foundry project name or ID
    FOUNDRY_IQ_ENDPOINT: The Foundry IQ API endpoint (optional, has default)

For v0.1, HTTP calls are real but gated behind the env var. If
FOUNDRY_IQ_PROJECT is not set, initialization raises a clear error.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from recall.store.base import (
    Atom,
    Memory,
    Pattern,
    Principle,
    Store,
    StoreStats,
)

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://api.foundry.microsoft.com/v1"


class FoundryIQStore(Store):
    """Store implementation backed by a Microsoft Foundry IQ knowledge base.

    All memories are stored as documents in a Foundry IQ KB, with grain
    level, provenance, and embedding vectors as metadata fields.

    For v0.1, this backend requires FOUNDRY_IQ_PROJECT to be set.
    Without it, initialization raises NotImplementedError with a
    pointer to docs/architecture.md.
    """

    def __init__(
        self,
        kb_name: str = "agent_memory",
        project: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        """Initialize the Foundry IQ store.

        Args:
            kb_name: Name of the knowledge base within the project.
            project: Foundry project name. Defaults to FOUNDRY_IQ_PROJECT env var.
            endpoint: API endpoint. Defaults to FOUNDRY_IQ_ENDPOINT or the standard URL.

        Raises:
            NotImplementedError: If FOUNDRY_IQ_PROJECT is not set.
        """
        self.project = project or os.environ.get("FOUNDRY_IQ_PROJECT")
        if not self.project:
            raise NotImplementedError(
                "Foundry IQ backend requires FOUNDRY_IQ_PROJECT environment variable. "
                "See docs/architecture.md for configuration details. "
                "Use SQLiteStore for offline development."
            )

        self.endpoint = endpoint or os.environ.get("FOUNDRY_IQ_ENDPOINT") or DEFAULT_ENDPOINT
        self.kb_name = kb_name

        # Authenticate using Azure DefaultCredential
        try:
            from azure.identity import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
            self._token = self._credential.get_token("https://foundry.microsoft.com/.default")
        except Exception as e:
            raise NotImplementedError(
                f"Failed to authenticate with Azure: {e}. "
                "Ensure azure-identity is installed and credentials are configured. "
                "See docs/architecture.md for setup instructions."
            ) from e

        self._base_url = f"{self.endpoint}/projects/{self.project}/kbs/{self.kb_name}"
        logger.info("Foundry IQ store initialized: %s/%s", self.project, self.kb_name)

    def _headers(self) -> dict[str, str]:
        """Build authenticated request headers."""
        return {
            "Authorization": f"Bearer {self._token.token}",
            "Content-Type": "application/json",
        }

    def _request(
        self, method: str, path: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated HTTP request to Foundry IQ.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to the KB base URL.
            data: Request body for POST/PUT.

        Returns:
            Response JSON as a dict.
        """
        import urllib.request

        url = f"{self._base_url}/{path}"
        body = json.dumps(data).encode() if data else None

        req = urllib.request.Request(
            url,
            data=body,
            headers=self._headers(),
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Foundry IQ request failed: %s %s -> %s", method, url, e)
            raise

    def write_atom(self, atom: Atom) -> str:
        """Persist an atom to the Foundry IQ knowledge base."""
        doc = {
            "id": atom.id,
            "type": "atom",
            "content": f"Q: {atom.prompt}\nA: {atom.answer}",
            "metadata": {
                "prompt": atom.prompt,
                "answer": atom.answer,
                "agent_id": atom.agent_id,
                "written_at": atom.written_at.isoformat(),
                "recall_count": atom.recall_count,
                "source_doc": atom.source_doc,
                "source_mtime": atom.source_mtime,
            },
        }
        self._request("POST", "documents", doc)
        return atom.id

    def write_pattern(self, pattern: Pattern) -> str:
        """Persist a pattern to the Foundry IQ knowledge base."""
        doc = {
            "id": pattern.id,
            "type": "pattern",
            "content": pattern.text,
            "metadata": {
                "derived_from": pattern.derived_from,
                "confidence": pattern.confidence,
                "written_at": pattern.written_at.isoformat(),
                "recall_count": pattern.recall_count,
            },
        }
        self._request("POST", "documents", doc)
        return pattern.id

    def write_principle(self, principle: Principle) -> str:
        """Persist a principle to the Foundry IQ knowledge base."""
        doc = {
            "id": principle.id,
            "type": "principle",
            "content": principle.text,
            "metadata": {
                "derived_from": principle.derived_from,
                "confidence": principle.confidence,
                "written_at": principle.written_at.isoformat(),
                "recall_count": principle.recall_count,
            },
        }
        self._request("POST", "documents", doc)
        return principle.id

    def search(self, query_embedding: bytes, grain: str, k: int = 5) -> list[Memory]:
        """Search the Foundry IQ KB using its native vector search.

        Foundry IQ handles embedding and similarity internally, so
        we pass the query text rather than raw vectors.
        """
        params: dict[str, object] = {
            "k": k,
        }
        if grain != "auto":
            params["filter"] = {"type": grain}

        result = self._request("POST", "search", params)
        documents = result.get("documents", [])

        memories: list[Memory] = []
        if isinstance(documents, list):
            for doc in documents:
                if not isinstance(doc, dict):
                    continue
                meta = doc.get("metadata", {})
                if not isinstance(meta, dict):
                    meta = {}

                mem = Memory(
                    memory=str(doc.get("content", "")),
                    grain=str(doc.get("type", "atom")),
                    confidence=float(meta.get("confidence", 0.5)),
                    freshness="unknown",
                    derived_from=meta.get("derived_from", []),
                    written_at=str(meta.get("written_at", "")),
                    last_recalled_at=None,
                    source_doc=meta.get("source_doc"),
                    agent_id=str(meta.get("agent_id", "default")),
                    id=str(doc.get("id", "")),
                )
                memories.append(mem)

        return memories

    def get(self, memory_id: str) -> Memory | None:
        """Retrieve a single memory by ID from Foundry IQ."""
        try:
            doc = self._request("GET", f"documents/{memory_id}")
            meta = doc.get("metadata", {})
            if not isinstance(meta, dict):
                meta = {}

            return Memory(
                memory=str(doc.get("content", "")),
                grain=str(doc.get("type", "atom")),
                confidence=float(meta.get("confidence", 0.5)),
                freshness="unknown",
                derived_from=meta.get("derived_from", []),
                written_at=str(meta.get("written_at", "")),
                last_recalled_at=None,
                id=str(doc.get("id", "")),
            )
        except Exception:
            return None

    def get_atom(self, atom_id: str) -> Atom | None:
        """Retrieve a single atom by ID from Foundry IQ."""
        try:
            doc = self._request("GET", f"documents/{atom_id}")
            meta = doc.get("metadata", {})
            if not isinstance(meta, dict):
                meta = {}

            return Atom(
                id=str(doc.get("id", "")),
                prompt=str(meta.get("prompt", "")),
                answer=str(meta.get("answer", "")),
                agent_id=str(meta.get("agent_id", "default")),
                written_at=datetime.fromisoformat(str(meta.get("written_at", ""))),
                recall_count=int(meta.get("recall_count", 0)),
                source_doc=meta.get("source_doc"),
                source_mtime=meta.get("source_mtime"),
            )
        except Exception:
            return None

    def get_pattern(self, pattern_id: str) -> Pattern | None:
        """Retrieve a single pattern by ID from Foundry IQ."""
        try:
            doc = self._request("GET", f"documents/{pattern_id}")
            meta = doc.get("metadata", {})
            if not isinstance(meta, dict):
                meta = {}

            return Pattern(
                id=str(doc.get("id", "")),
                text=str(doc.get("content", "")),
                derived_from=meta.get("derived_from", []),
                confidence=float(meta.get("confidence", 0.0)),
                written_at=datetime.fromisoformat(str(meta.get("written_at", ""))),
                recall_count=int(meta.get("recall_count", 0)),
            )
        except Exception:
            return None

    def all_atoms(self, since: datetime | None = None) -> Iterator[Atom]:
        """List all atoms from the Foundry IQ KB."""
        params: dict[str, object] = {"filter": {"type": "atom"}, "limit": 1000}
        if since:
            params["filter"]["written_after"] = since.isoformat()  # type: ignore[index]

        result = self._request("POST", "list", params)
        documents = result.get("documents", [])

        if isinstance(documents, list):
            for doc in documents:
                if not isinstance(doc, dict):
                    continue
                meta = doc.get("metadata", {})
                if not isinstance(meta, dict):
                    meta = {}

                yield Atom(
                    id=str(doc.get("id", "")),
                    prompt=str(meta.get("prompt", "")),
                    answer=str(meta.get("answer", "")),
                    agent_id=str(meta.get("agent_id", "default")),
                    written_at=datetime.fromisoformat(
                        str(meta.get("written_at", datetime.now(UTC).isoformat()))
                    ),
                    recall_count=int(meta.get("recall_count", 0)),
                    source_doc=meta.get("source_doc"),
                    source_mtime=meta.get("source_mtime"),
                )

    def all_patterns(self, since: datetime | None = None) -> Iterator[Pattern]:
        """List all patterns from the Foundry IQ KB."""
        params: dict[str, object] = {"filter": {"type": "pattern"}, "limit": 1000}
        result = self._request("POST", "list", params)
        documents = result.get("documents", [])

        if isinstance(documents, list):
            for doc in documents:
                if not isinstance(doc, dict):
                    continue
                meta = doc.get("metadata", {})
                if not isinstance(meta, dict):
                    meta = {}

                yield Pattern(
                    id=str(doc.get("id", "")),
                    text=str(doc.get("content", "")),
                    derived_from=meta.get("derived_from", []),
                    confidence=float(meta.get("confidence", 0.0)),
                    written_at=datetime.fromisoformat(
                        str(meta.get("written_at", datetime.now(UTC).isoformat()))
                    ),
                    recall_count=int(meta.get("recall_count", 0)),
                )

    def all_principles(self) -> Iterator[Principle]:
        """List all principles from the Foundry IQ KB."""
        params: dict[str, object] = {"filter": {"type": "principle"}, "limit": 1000}
        result = self._request("POST", "list", params)
        documents = result.get("documents", [])

        if isinstance(documents, list):
            for doc in documents:
                if not isinstance(doc, dict):
                    continue
                meta = doc.get("metadata", {})
                if not isinstance(meta, dict):
                    meta = {}

                yield Principle(
                    id=str(doc.get("id", "")),
                    text=str(doc.get("content", "")),
                    derived_from=meta.get("derived_from", []),
                    confidence=float(meta.get("confidence", 0.0)),
                    written_at=datetime.fromisoformat(
                        str(meta.get("written_at", datetime.now(UTC).isoformat()))
                    ),
                    recall_count=int(meta.get("recall_count", 0)),
                )

    def update_atom(self, atom: Atom) -> None:
        """Update an existing atom in Foundry IQ."""
        doc = {
            "id": atom.id,
            "type": "atom",
            "content": f"Q: {atom.prompt}\nA: {atom.answer}",
            "metadata": {
                "prompt": atom.prompt,
                "answer": atom.answer,
                "agent_id": atom.agent_id,
                "written_at": atom.written_at.isoformat(),
                "recall_count": atom.recall_count,
                "source_doc": atom.source_doc,
                "superseded_by": atom.superseded_by,
                "decayed": atom.decayed,
            },
        }
        self._request("PUT", f"documents/{atom.id}", doc)

    def update_pattern(self, pattern: Pattern) -> None:
        """Update an existing pattern in Foundry IQ."""
        doc = {
            "id": pattern.id,
            "type": "pattern",
            "content": pattern.text,
            "metadata": {
                "derived_from": pattern.derived_from,
                "confidence": pattern.confidence,
                "written_at": pattern.written_at.isoformat(),
                "recall_count": pattern.recall_count,
            },
        }
        self._request("PUT", f"documents/{pattern.id}", doc)

    def delete(self, memory_id: str) -> None:
        """Delete a memory from Foundry IQ."""
        try:
            self._request("DELETE", f"documents/{memory_id}")
        except Exception:
            logger.warning("Failed to delete document %s from Foundry IQ", memory_id)

    def stats(self) -> StoreStats:
        """Get aggregate statistics from Foundry IQ."""
        try:
            result = self._request("GET", "stats")
            return StoreStats(
                total_atoms=int(str(result.get("atom_count", 0))),
                total_patterns=int(str(result.get("pattern_count", 0))),
                total_principles=int(str(result.get("principle_count", 0))),
            )
        except Exception:
            return StoreStats()

    def close(self) -> None:
        """Release resources (no-op for HTTP-based store)."""
        pass
