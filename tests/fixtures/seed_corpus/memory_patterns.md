# Agent Memory Patterns

This document describes common patterns for implementing memory
in AI agent systems. These patterns emerged from building production
agents that need to learn from their interactions.

## The Q&A Atom Pattern

The simplest unit of agent memory is a question-answer pair. When
an agent answers a question, the pair is stored as an "atom" -- the
fundamental building block of memory.

Atoms are cheap to create, fast to search, and easy to understand.
They carry provenance: which agent created them, when, and from
what source. This makes them trustworthy in a way that raw vector
store entries are not.

## The Promotion Pattern

Individual atoms are noisy. Five atoms about the same topic may
agree on a common claim but phrase it differently. The promotion
pattern consolidates these into a single "pattern" -- a higher-grain
memory with explicit confidence.

Promotion requires agreement: a judge (model or heuristic) must
confirm that the atoms say the same thing. This prevents premature
generalization from contradicting observations.

## The Decay Pattern

Not all memories are equally valuable over time. An atom from six
months ago about a since-deprecated API should fade from search
results. Exponential decay implements this: memories lose weight
over time unless they continue to be recalled.

Decay does not delete. The atom remains in the store for provenance
(patterns that reference it still need it). But it stops appearing
in search results, keeping the active memory surface relevant.

## The Healing Pattern

Contradictions are inevitable in any long-lived system. Two atoms
may disagree because the underlying truth changed, because different
sources conflict, or because the agent was simply wrong once.

Healing actively detects these contradictions and resolves them
using the same confidence and recency signals that power retrieval.
The loser is tagged as superseded, not deleted. The human can
review the healing log at their convenience.
