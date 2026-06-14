"""Source-mtime freshness checking for recall atoms.

For atoms with a source_doc path, compares the current file modification
time against the stored source_mtime. For HTTP sources, optionally sends
a HEAD request for the Last-Modified header.

Returns one of three verdicts: "fresh", "stale", "unknown".
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from recall.store.base import Atom

logger = logging.getLogger(__name__)


def check_freshness(atom: Atom) -> str:
    """Check whether an atom's source document has changed.

    Args:
        atom: The atom to check. Must have source_doc set.

    Returns:
        "fresh" if source_mtime matches current mtime,
        "stale" if source has been modified since the atom was written,
        "unknown" if source_doc is not set or file cannot be accessed.
    """
    if not atom.source_doc:
        return "unknown"

    source = atom.source_doc

    # HTTP sources
    if source.startswith("http://") or source.startswith("https://"):
        return _check_http_freshness(source, atom.source_mtime)

    # Local file sources
    return _check_file_freshness(source, atom.source_mtime)


def _check_file_freshness(path: str, stored_mtime: float | None) -> str:
    """Check freshness of a local file source.

    Args:
        path: Path to the source file.
        stored_mtime: The mtime recorded when the atom was created.

    Returns:
        "fresh", "stale", or "unknown".
    """
    try:
        file_path = Path(path)
        if not file_path.exists():
            logger.debug("Source file not found: %s", path)
            return "unknown"

        current_mtime = file_path.stat().st_mtime

        if stored_mtime is None:
            return "unknown"

        if abs(current_mtime - stored_mtime) < 0.01:
            return "fresh"

        return "stale"

    except OSError as e:
        logger.debug("Error checking source file %s: %s", path, e)
        return "unknown"


def _check_http_freshness(url: str, stored_mtime: float | None) -> str:
    """Check freshness of an HTTP source via HEAD request.

    Only runs if network access is available. Falls back to 'unknown'
    on any error to avoid blocking the agent.

    Args:
        url: The HTTP URL of the source.
        stored_mtime: The stored mtime (from Last-Modified header).

    Returns:
        "fresh", "stale", or "unknown".
    """
    if stored_mtime is None:
        return "unknown"

    try:
        import urllib.request

        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as response:
            last_modified = response.headers.get("Last-Modified")
            if not last_modified:
                return "unknown"

            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(last_modified)
            current_mtime = dt.timestamp()

            if abs(current_mtime - stored_mtime) < 1.0:
                return "fresh"
            return "stale"

    except Exception as e:
        logger.debug("Error checking HTTP source %s: %s", url, e)
        return "unknown"


def get_file_mtime(path: str) -> float | None:
    """Get the current modification time of a file.

    Args:
        path: Path to the file.

    Returns:
        The mtime as a float, or None if the file cannot be accessed.
    """
    try:
        return os.path.getmtime(path)
    except OSError:
        return None
