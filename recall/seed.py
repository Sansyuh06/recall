"""Seed recall memory from existing content.

Walks markdown, text, PDF, and OpenAPI files to extract Q->A pairs
and writes them as atoms with source_doc populated for freshness tracking.
Triggers one immediate promotion pass at the end so the seeded KB
already has patterns.

Usage:
    recall seed --from ./docs
    recall seed --from ./openapi.yaml
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from recall.embeddings import embed, embedding_to_bytes
from recall.freshness import get_file_mtime
from recall.promote import PromoteWorker
from recall.store.base import Atom, Store

logger = logging.getLogger(__name__)

# File extensions to process
SUPPORTED_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json", ".pdf"}


def from_path(
    path: Path,
    store: Store,
    agent_id: str = "seed",
) -> int:
    """Seed the store from files at the given path.

    Walks directories recursively, processes each supported file,
    extracts Q->A pairs, writes atoms, then runs one promotion pass.

    Args:
        path: A file or directory to seed from.
        store: The storage backend.
        agent_id: Agent ID to attribute seeded atoms to.

    Returns:
        Number of atoms created.
    """
    path = Path(path)
    total = 0

    if path.is_file():
        total += _process_file(path, store, agent_id)
    elif path.is_dir():
        for file_path in sorted(path.rglob("*")):
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                total += _process_file(file_path, store, agent_id)
    else:
        logger.warning("Path does not exist: %s", path)
        return 0

    # Run one promotion pass so seeded KB already has patterns
    if total > 0:
        promoter = PromoteWorker(store)
        promoted = promoter.run_once()
        logger.info(
            "Seeded %d atoms, promoted %d patterns/principles",
            total,
            len(promoted),
        )

    return total


def _process_file(
    file_path: Path,
    store: Store,
    agent_id: str,
) -> int:
    """Process a single file and extract Q->A atoms.

    Args:
        file_path: Path to the file.
        store: The storage backend.
        agent_id: Agent ID for attribution.

    Returns:
        Number of atoms created from this file.
    """
    suffix = file_path.suffix.lower()
    mtime = get_file_mtime(str(file_path))

    try:
        if suffix == ".pdf":
            pairs = _extract_from_pdf(file_path)
        elif suffix in (".yaml", ".yml"):
            pairs = _extract_from_openapi(file_path)
        elif suffix == ".json":
            pairs = _extract_from_json(file_path)
        else:
            pairs = _extract_from_markdown(file_path)
    except Exception as e:
        logger.warning("Failed to process %s: %s", file_path, e)
        return 0

    count = 0
    for prompt, answer in pairs:
        if len(answer.strip()) < 20:
            continue

        combined = f"{prompt} {answer}"
        vec = embed(combined)

        atom = Atom(
            prompt=prompt,
            answer=answer,
            embedding=embedding_to_bytes(vec),
            agent_id=agent_id,
            written_at=datetime.now(UTC),
            source_doc=str(file_path),
            source_mtime=mtime,
        )
        store.write_atom(atom)
        count += 1

    return count


def _extract_from_markdown(file_path: Path) -> list[tuple[str, str]]:
    """Extract Q->A pairs from a markdown file.

    Uses headings as questions and the body text below each heading
    as the answer.
    """
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return _extract_heading_pairs(text)


def _extract_heading_pairs(text: str) -> list[tuple[str, str]]:
    """Split text by headings and pair each heading with its body."""
    lines = text.split("\n")
    pairs: list[tuple[str, str]] = []
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        heading_match = re.match(r"^(#{1,4})\s+(.+)", line)
        if heading_match:
            if current_heading and current_body:
                body = "\n".join(current_body).strip()
                if body:
                    pairs.append((current_heading, body))
            current_heading = heading_match.group(2).strip()
            current_body = []
        else:
            current_body.append(line)

    # Last section
    if current_heading and current_body:
        body = "\n".join(current_body).strip()
        if body:
            pairs.append((current_heading, body))

    return pairs


def _extract_from_pdf(file_path: Path) -> list[tuple[str, str]]:
    """Extract Q->A pairs from a PDF file.

    Requires pypdf. Extracts text page by page and uses paragraph
    boundaries as Q->A splits.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning(
            "pypdf not installed, skipping PDF file: %s. "
            "Install with: pip install recall-agent[pdf]",
            file_path,
        )
        return []

    reader = PdfReader(str(file_path))
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"

    return _extract_heading_pairs(full_text)


def _extract_from_openapi(file_path: Path) -> list[tuple[str, str]]:
    """Extract Q->A pairs from an OpenAPI YAML/JSON spec.

    Uses endpoint paths as questions and descriptions/summaries as answers.
    """
    try:
        import yaml
    except ImportError:
        # Fall back to treating as markdown
        return _extract_from_markdown(file_path)

    text = file_path.read_text(encoding="utf-8", errors="replace")
    try:
        spec = yaml.safe_load(text)
    except Exception:
        return _extract_from_markdown(file_path)

    if not isinstance(spec, dict):
        return []

    pairs: list[tuple[str, str]] = []

    # Extract API info
    info = spec.get("info", {})
    if info.get("description"):
        pairs.append((f"What is {info.get('title', 'this API')}?", info["description"]))

    # Extract paths
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, details in methods.items():
            if not isinstance(details, dict):
                continue
            summary = details.get("summary", "")
            description = details.get("description", "")
            answer = f"{summary}\n{description}".strip()
            if answer:
                pairs.append((f"What does {method.upper()} {path} do?", answer))

    return pairs


def _extract_from_json(file_path: Path) -> list[tuple[str, str]]:
    """Extract Q->A pairs from a JSON file.

    Handles OpenAPI JSON specs and simple key-value documents.
    """
    text = file_path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _extract_from_markdown(file_path)

    # If it looks like an OpenAPI spec, delegate
    if isinstance(data, dict) and "openapi" in data:
        return _extract_from_openapi(file_path)

    # Simple key-value
    pairs: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str) and len(value) >= 20:
                pairs.append((f"What is {key}?", value))

    return pairs
