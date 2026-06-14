# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-14

### Added

- `@remember` decorator for wrapping agent functions with memory
- `memoriagrain()` tool injection for OpenAI-compatible agents
- Three-grain memory hierarchy: atoms, patterns, principles
- Three-gate promotion algorithm (density, agreement, recency)
- Exponential decay with configurable half-life
- Active contradiction resolution via `memoriagrain heal`
- Source-mtime freshness checking
- Provenance tracking with `derived_from` chains
- SQLite backend for offline-safe storage
- Foundry IQ backend (gated behind `FOUNDRY_IQ_PROJECT` env var)
- Deterministic agreement judge fallback (no API key required)
- CLI with 6 active verbs: `seed`, `stats`, `heal`, `replay`, `diff`, `forget`
- Claude Code plugin manifest with Stop hook for continuous learning
- Pre-tool hook for redundant call detection
- Cross-agent memory inheritance with visible attribution
- `MEMORY.md` conviction document
- Real before/after examples with captured terminal output

[0.1.0]: https://github.com/Sansyuh06/memoriagrain/releases/tag/v0.1.0
