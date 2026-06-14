# Architecture

This document describes the architecture of `memoriagrain` for contributors
and advanced users.

## Design principles

1. **Memory as a tool, not a prefix.** The model decides when to remember.
2. **Three-grain hierarchy.** Atoms consolidate into patterns, patterns
   into principles. Each level is more stable and higher confidence.
3. **Provenance everywhere.** Every memory carries its chain of evidence.
4. **Offline-safe by default.** SQLite runs without any network dependency.
5. **Enterprise-ready as an option.** Foundry IQ provides the shared,
   managed backend for production deployments.

## Module dependency graph

```
cli.py
  -> seed.py, heal.py, diff.py, tool.py
    -> promote.py, decay.py, freshness.py, confidence.py
      -> judge.py, embeddings.py
        -> store/base.py
          -> store/sqlite.py | store/foundry_iq.py
```

## Storage backends

### SQLite (default)

The `SQLiteStore` uses a local database with three tables (atoms,
patterns, principles) and a meta table for configuration. Embedding
vectors are stored as BLOBs (numpy arrays serialized with tobytes).
Cosine similarity search is performed in Python by loading all vectors
and computing dot products. This is sufficient for stores up to ~100K
atoms. Beyond that, consider FAISS or the Foundry IQ backend.

### Foundry IQ (enterprise)

The `FoundryIQStore` uses Microsoft Foundry IQ's REST API for storage
and search. Authentication uses `DefaultAzureCredential`. The backend
leverages Foundry IQ's native vector search, so cosine similarity is
computed server-side.

Required environment:
- `FOUNDRY_IQ_PROJECT`: The Foundry project name
- `FOUNDRY_IQ_ENDPOINT`: API endpoint (optional, uses default)

## Embedding strategy

The default embedding model is `all-MiniLM-L6-v2` from sentence-transformers
(384 dimensions, runs locally, no API key). If sentence-transformers is
not installed, a deterministic fallback using character n-gram hashing
is used. This is adequate for testing but not for production.

For production quality, set `OPENAI_API_KEY` and `RECALL_EMBEDDINGS=openai`
to use `text-embedding-3-small` (1536 dimensions).

Embeddings are cached on disk in `.memoriagrain/embed_cache/` keyed by SHA-256
of the input text.

## Agreement judge

The judge determines whether a cluster of atoms agrees on a common claim.
Two implementations:

1. **OpenAI path** (when `OPENAI_API_KEY` is set): Sends atom answers to
   gpt-4o-mini with JSON response format. Returns `{common_claim, disagreement}`.

2. **Heuristic path** (default): Uses `difflib.SequenceMatcher` to compute
   pairwise similarity across atom answers. Disagreement = 1 - mean(ratio).
   The most representative answer (highest average similarity) is chosen as
   the common claim.

The heuristic path makes tests hermetic and allows the system to function
without any API keys.

## Configuration

Runtime configuration is stored in the SQLite meta table:

- `promotion.strictness`: "loose", "default", or "strict"
- `hooks.pre_tool`: "true" or "false"

Access via `memoriagrain config get/set KEY VALUE`.
