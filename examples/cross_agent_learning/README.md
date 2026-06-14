# Cross-Agent Learning

Two agents share a SQLite store. Agent A (search) learns from research,
Agent B (review) inherits that knowledge visibly.

## What it demonstrates

1. **agent_search.py** answers 3 questions and writes atoms to a shared DB
2. **agent_review.py** queries the same DB for a related topic
3. The review agent's output shows the inheritance line:
   ```
   3 atoms inherited from agent_search (written just now)
   ```

This is the cross-agent learning feature: memory is shared, not
synchronized. Agent B discovers Agent A's work through normal memoriagrain,
with visible attribution.

## Running

```bash
bash run.sh
```

Output is captured to `captured/agent_search.txt` and `captured/agent_review.txt`.
