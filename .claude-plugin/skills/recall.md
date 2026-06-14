# recall -- Memory tool for Claude Code

## When to use recall

- Call `recall(query)` when you are about to answer a question that the user or a similar agent has asked before.
- Call `recall(query, grain="pattern")` when you want consolidated knowledge rather than individual observations.
- Prefer `grain="auto"` (the default) to let recall choose the best grain level.

## When to seed

Run `recall seed --from ./docs` at the start of a new project to pre-populate memory from existing documentation. This gives you patterns from day one instead of waiting for them to accumulate.

## When to heal

Run `recall heal` when:
- You notice contradictory answers in your recall results
- After a significant codebase change that might invalidate past observations
- Periodically (weekly) to keep the memory store clean

Use `recall heal --dry-run` first to preview what would change.

## What you get back

Every recall returns:
- The memory text
- The grain level (atom, pattern, or principle)
- A confidence score (0.0 to 1.0)
- A freshness verdict (fresh, stale, or unknown)
- The provenance chain (derived_from IDs)

Use the confidence score to decide how much to trust the memory. Below 0.3, treat it as a weak signal. Above 0.7, it is reliable.

## Reading the inheritance line

When memories come from other agents, you will see a line like:
```
3 patterns inherited from agent_search (written 2 days ago)
```
This means another agent working on the same project discovered this knowledge. Use it, but verify if the context has changed.

## Commands

- `recall stats` -- see what is in memory
- `recall heal` -- fix contradictions
- `recall seed --from PATH` -- populate from docs
- `recall replay --since 7d` -- see recent memory growth
- `recall diff --against last-deploy` -- check for stale memories
- `recall forget --pattern "old API"` -- remove outdated memories
