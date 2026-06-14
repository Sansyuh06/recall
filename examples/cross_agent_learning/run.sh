#!/bin/bash
# Run the cross-agent learning example and capture output.
# Usage: bash run.sh

set -e
cd "$(dirname "$0")"
mkdir -p captured

SHARED_DB=$(mktemp -d)/shared_memoriagrain.db

echo "Running agent_search.py..."
uv run python agent_search.py "$SHARED_DB" 2>&1 | tee captured/agent_search.txt

echo ""
echo "Running agent_review.py..."
uv run python agent_review.py "$SHARED_DB" 2>&1 | tee captured/agent_review.txt

echo ""
echo "Done. Captured output in ./captured/"
