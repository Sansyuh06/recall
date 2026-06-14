# The Three-Gate Promotion Algorithm

How atoms become patterns, and patterns become principles.

## Overview

Promotion is the process of consolidating individual observations (atoms)
into reliable claims (patterns) and then into stable generalizations
(principles). It is not automatic -- three gates must pass, each testing
a different dimension of memory quality.

## Gate 1: Density

The first gate checks whether enough atoms exist in the same semantic
region to justify consolidation. A cluster is formed when N or more atoms
have pairwise cosine similarity above a threshold.

| Strictness | Min cluster size (N) | Cosine threshold |
|------------|---------------------|------------------|
| loose      | 3                   | 0.75             |
| default    | 5                   | 0.82             |
| strict     | 7                   | 0.88             |

Clustering uses a greedy approach: for each unassigned atom, find all
atoms within the cosine threshold and form a cluster. An atom belongs
to at most one cluster (first-match wins).

The embedding vectors are stored alongside each atom in the store.
For SQLite, cosine similarity is computed in Python over BLOB-stored
numpy arrays. For Foundry IQ, the native vector search handles this
server-side.

## Gate 2: Agreement

Density alone is not enough. Five atoms about "the default port" might
include one that says 8080 and another that says 3000. The agreement
gate uses a judge to determine whether the cluster actually agrees.

The judge reads all atoms in the cluster and produces:
```json
{
  "common_claim": "The service runs on port 8080 by default.",
  "disagreement": 0.15
}
```

Promotion proceeds only if `disagreement < max_disagreement`:

| Strictness | Max disagreement |
|------------|-----------------|
| loose      | 0.3             |
| default    | 0.2             |
| strict     | 0.1             |

### Judge implementations

**OpenAI path** (when `OPENAI_API_KEY` is set): Uses gpt-4o-mini with
JSON response format. The model is given all atom Q&A pairs and asked
to extract the common claim and rate disagreement on a 0-1 scale.

**Deterministic fallback** (default): Uses `difflib.SequenceMatcher` to
compute pairwise similarity ratios across atom answers. Disagreement is
`1 - mean(pairwise_ratio)`. The most representative answer (highest
average similarity to all others) is chosen as the common claim.

The model-as-agreement-judge is the differentiator versus naive cosine
clustering. It catches semantic contradictions that similar embeddings
would miss.

## Gate 3: Recency

A cluster of old, never-recalled atoms should not promote. The recency
gate ensures that the cluster is actively relevant:

| Strictness | Min recently recalled | Recency window |
|------------|----------------------|----------------|
| loose      | 1                    | 60 days        |
| default    | 2                    | 30 days        |
| strict     | 3                    | 14 days        |

An atom counts as "recently recalled" if its `last_recalled_at` timestamp
falls within the recency window.

## Promotion output

When all three gates pass:

1. A new **Pattern** is created with:
   - `text` = the judge's `common_claim`
   - `derived_from` = list of atom IDs in the cluster
   - `confidence` = 1 - disagreement
   - `embedding` = embed(common_claim)
   - `written_at` = now

2. Each contributing atom is marked with `promoted_into_pattern_id`
   pointing to the new pattern. Atoms are not deleted -- provenance
   depends on them remaining in the store.

## Pattern-to-principle promotion

The same three gates apply one layer up. Patterns are treated as
pseudo-atoms for clustering purposes. When a cluster of patterns
passes all three gates, a **Principle** is created with `derived_from`
pointing to the pattern IDs.

## Idempotence

The promotion worker skips atoms already marked as promoted and patterns
already promoted to principles. Running `promote.run_once()` multiple
times is safe and produces no duplicate patterns or principles.

## Configuration

Set strictness via the CLI:
```bash
memoriagrain config set promotion.strictness strict
```

Or programmatically:
```python
from memoriagrain.promote import PromoteWorker
worker = PromoteWorker(store, strictness="strict")
worker.run_once()
```

## Integration with heal

The `memoriagrain heal` command runs a promotion pass before contradiction
resolution. This ensures that any promotable clusters are consolidated
before the heal worker looks for disagreements.
