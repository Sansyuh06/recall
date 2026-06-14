# Claude Code Plugin

How to use recall as a Claude Code plugin.

## Installation

```
/plugin install memoriagrain@memoriagrain
```

This registers:
- The `memoriagrain` skill (teaches Claude Code when to call memory)
- A Stop hook (writes atoms from session transcripts)
- Commands: `memoriagrain-stats`, `memoriagrain-heal`, `memoriagrain-seed`

## How the Stop hook works

When you end a Claude Code session:

1. Claude Code fires the PostToolUse hook on the Stop event
2. `python -m memoriagrain.hooks.claude_code_stop` reads the session transcript
3. Extracts Q&A pairs (user question + assistant answer)
4. Filters: skips short answers, clarification questions, error responses
5. Writes accepted pairs as atoms with session attribution
6. Output: `[memoriagrain] wrote N atoms from session <id>`

## Continuous learning

Over multiple sessions, memoriagrain accumulates knowledge:
- Session 1: 5 atoms about authentication
- Session 2: 3 atoms about deployment
- Session 3: memoriagrain notices the auth atoms cluster, promotes to a pattern

The pattern is now available to future sessions with higher confidence
than any individual atom.

## Commands

### memoriagrain-stats

Shows memory statistics: atom count, pattern count, agents, oldest/newest.

### memoriagrain-heal

Runs contradiction resolution. Useful after a codebase change.

### memoriagrain-seed

Pre-populate memory from documentation:
```
memoriagrain seed --from ./docs
```

## Configuration

Configure recall behavior for Claude Code:

```bash
# Set promotion strictness
memoriagrain config set promotion.strictness default

# Enable pre-tool hints (warns about redundant tool calls)
memoriagrain config set hooks.pre_tool true
```

## Local development

The plugin uses a local SQLite store at `.memoriagrain/memoriagrain.db` by default.
This file is excluded from git by the standard `.gitignore`.

To connect to a Foundry IQ backend instead:
```bash
export FOUNDRY_IQ_PROJECT=your-project
```
