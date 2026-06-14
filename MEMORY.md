# What memory means for AI agents

A note on why `memoriagrain` exists in the shape it does.


## Memory is not storage

Most "agent memory" libraries store strings and retrieve them by
cosine similarity. That is not memory -- it is a vector database
with a friendlier name.

Real memory has structure. Events that recede. Patterns that emerge
from repetition. Principles that consolidate when enough patterns
agree. Each layer is more stable, more confident, and more expensive
to overturn than the one below it.

Real memory also has uncertainty. A claim observed once is a data
point. Observed five times with agreement, it is a pattern worth
trusting. Observed in conflict with a newer source, it is a
contradiction that demands resolution -- not silent overwriting.

`memoriagrain` implements this hierarchy as three grain levels: atoms
(individual observations), patterns (consolidated claims from
agreeing atoms), and principles (generalizations from agreeing
patterns). Each promotion requires passing three explicit gates.
The algorithm is documented in
[docs/promotion-algorithm.md](./docs/promotion-algorithm.md).


## Memory must be the agent's choice

Existing systems inject memory into the system prompt as a prefix.
The model pays the token cost whether the memory was useful or not.
The model cannot choose to ignore an irrelevant memory. The human
reading the agent's trace cannot see that memory was silently
injected, or which memories influenced the response.

This is expensive, invisible, and uncontrollable.

`memoriagrain` makes memory a tool the model calls. The model sees
`memoriagrain` in its tool list and decides when to query, what to query
for, and whether to use the result. The memoriagrain step appears in the
trace with the full response: grain, confidence, freshness, and
provenance chain. Memory becomes auditable.

When a model calls `memoriagrain(query="how does auth work?")`, the
reader of the trace knows exactly what was asked and what was
returned. When a model does not call recall, the reader knows
memory was not a factor. Visibility is not a feature. It is the
minimum requirement.


## Memory must have provenance

A memory without a chain of evidence is a hallucination waiting
to fire. "The default port is 8080" is useful. "The default port
is 8080, derived from five consistent observations across three
sessions, last confirmed two days ago against the current source
document" is trustworthy.

Every memoriagrain response in this system returns:

- **grain** -- atom, pattern, or principle
- **confidence** -- a continuous score reflecting grain bonus,
  recency, and agreement level
- **freshness** -- whether the source document has changed since
  the memory was written
- **derived_from** -- the chain of atom IDs that support the claim

If the system cannot show why a memory exists, the memory is not
returned. There is no "trust me" mode.


## Memory must heal

Two atoms can contradict each other. This is not an edge case. It
is the normal state of any system that learns continuously.

Sources change. The API that used port 8080 last month now uses
3000. An atom from a Tuesday session says one thing; an atom from
Wednesday says another. A pattern's confidence collapses as new
evidence arrives that disagrees with its claim.

Ignoring contradictions is not an option. Silent overwriting is
not an option. The only acceptable behavior is active resolution:
detect the conflict, pick a winner using the same signals that
power retrieval (confidence, recency), mark the loser as
superseded (not deleted -- provenance depends on it), and write
a log that the developer can review.

`memoriagrain heal` does this. It runs a promotion pass first (to
consolidate anything promotable), then scans for contradicting
clusters, resolves them, and writes the resolution to a log file.
The `--dry-run` flag shows what would change without applying it.


## Memory must grow without ceremony

A memory system that requires the developer to write to it will
not be written to. Intent decays. Discipline varies. The backlog
of "things I should remember" grows until it is abandoned.

The only sustainable approach is to extract memory from work that
already happened. In Claude Code, the Stop hook fires at the end
of every session, reads the transcript, extracts substantive Q&A
pairs, and writes them as atoms. No ceremony. No extra command.
The developer's normal workflow produces memory as a byproduct.

Over time, atoms cluster. The promotion algorithm detects agreement.
Patterns emerge. The KB that started empty after installation
becomes useful after a week of normal work, without the developer
ever explicitly writing to it.

This is the feature that makes people keep the tool installed.


## Memory is shared, not synchronized

When two agents share a Foundry IQ knowledge base -- or even a
local SQLite file -- they do not synchronize memories. There is no
replication protocol, no conflict-free data type, no merge strategy.

They share a substrate. Agent B asking about authentication discovers
Agent A's pattern from yesterday. The inheritance line appears in
the response:

```
3 patterns inherited from agent_search (written 2 days ago)
```

The agent sees it. The human reading the trace sees it. The
provenance chain traces back to Agent A's original atoms. This is
not a feature that was designed separately. It is what falls out
when memory lives where work already lives, and every memory
carries its author.


## What we will not do

- We will not silently inject memory the model did not ask for.
  Memory is a tool the model calls, or it is not used.

- We will not retrieve a memory without provenance. Every response
  includes grain, confidence, freshness, and derived_from.

- We will not let a memory outlive its source document without
  warning. Freshness checking runs on every retrieval for atoms
  with a known source path.

- We will not let the memory store grow unbounded. Exponential
  decay marks old, unreferenced atoms as decayed. They remain for
  provenance but stop appearing in search results.

- We will not paper over contradictions. When atoms disagree, the
  heal worker resolves the conflict explicitly and writes a log.

These are the constraints. `memoriagrain` is what remains when you build
a memory system inside them.
