# Claude Code Plugin

How to use recall as a Claude Code plugin.

## Installation

```
/plugin install recall@recall
```

This registers:
- The `recall` skill (teaches Claude Code when to call memory)
- A Stop hook (writes atoms from session transcripts)
- Commands: `recall-stats`, `recall-heal`, `recall-seed`

## How the Stop hook works

When you end a Claude Code session:

1. Claude Code fires the PostToolUse hook on the Stop event
2. `python -m recall.hooks.claude_code_stop` reads the session transcript
3. Extracts Q&A pairs (user question + assistant answer)
4. Filters: skips short answers, clarification questions, error responses
5. Writes accepted pairs as atoms with session attribution
6. Output: `[recall] wrote N atoms from session <id>`

## Continuous learning

Over multiple sessions, recall accumulates knowledge:
- Session 1: 5 atoms about authentication
- Session 2: 3 atoms about deployment
- Session 3: recall notices the auth atoms cluster, promotes to a pattern

The pattern is now available to future sessions with higher confidence
than any individual atom.

## Commands

### recall-stats

Shows memory statistics: atom count, pattern count, agents, oldest/newest.

### recall-heal

Runs contradiction resolution. Useful after a codebase change.

### recall-seed

Pre-populate memory from documentation:
```
recall seed --from ./docs
```

## Configuration

Configure recall behavior for Claude Code:

```bash
# Set promotion strictness
recall config set promotion.strictness default

# Enable pre-tool hints (warns about redundant tool calls)
recall config set hooks.pre_tool true
```

## Local development

The plugin uses a local SQLite store at `.recall/recall.db` by default.
This file is excluded from git by the standard `.gitignore`.

To connect to a Foundry IQ backend instead:
```bash
export FOUNDRY_IQ_PROJECT=your-project
```
