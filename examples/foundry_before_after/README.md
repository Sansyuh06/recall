# Before / After: Foundry Agent with memoriagrain

This example demonstrates the difference between a naive agent and one
using `@remember` with memoriagrain memory.

## What it does

1. **before.py** answers 5 questions about Foundry IQ without memory.
   Each question is answered independently, including a repeated question
   that gets re-computed from scratch.

2. **after.py** answers the same 5 questions with memoriagrain:
   - Seeds memory from `seed/` documentation first
   - Checks memoriagrain before calling the LLM
   - Writes new Q&A atoms after each LLM call
   - The repeated question (Q4) hits memory instead of re-computing

## Running

```bash
bash run.sh
```

Output is captured to `captured/before.txt` and `captured/after.txt`.

## About the stub LLM

If no `OPENAI_API_KEY` is set, both scripts use a deterministic stub
LLM that reads from `seed/qa_fixtures.json`. Token counts are
approximate (word-split), latency is simulated from a fixed table,
and costs are computed at $0.01/1K tokens.

Captured output reflects the stub LLM. Real LLM numbers will vary.
