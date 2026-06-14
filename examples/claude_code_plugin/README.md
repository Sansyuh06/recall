# Claude Code Plugin

Install recall as a Claude Code plugin for continuous learning.

## Installation

```
/plugin install recall@recall
```

## What happens

1. The `recall` skill is registered, teaching Claude Code when to call
   the recall tool during your sessions.

2. A **Stop hook** fires at the end of every session. It reads the
   session transcript, extracts substantive Q&A turns, and writes
   them as atoms to your local recall store.

3. Over time, your recall store accumulates knowledge from your work.
   The next session can recall what you learned yesterday.

## Using recall commands

After installation, these commands are available:

```
recall stats        # See what's in memory
recall heal         # Fix contradictions
recall seed --from ./docs  # Populate from existing docs
```

## How the Stop hook works

When you end a Claude Code session (`/quit` or session timeout):

1. Claude Code invokes `python -m recall.hooks.claude_code_stop`
2. The hook reads the session transcript from stdin
3. It extracts Q&A pairs (user question followed by assistant answer)
4. Filters out: short answers (<50 chars), clarification questions, errors
5. Writes accepted pairs as atoms with session attribution
6. Prints `[recall] wrote N atoms from session <id>` to stderr

You don't need to do anything. Memory grows as a byproduct of your
normal work.

## Checking memory growth

After a few sessions:

```
recall stats
```

Shows how many atoms, patterns, and principles have accumulated.

```
recall replay --since 7d
```

Shows a timeline of memory growth over the past week.
