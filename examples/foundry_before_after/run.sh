#!/bin/bash
# Run the before/after comparison and capture output.
# Usage: bash run.sh

set -e
cd "$(dirname "$0")"
mkdir -p captured

echo "Running before.py (no memoriagrain)..."
uv run python before.py 2>&1 | tee captured/before.txt

echo ""
echo "Running after.py (with memoriagrain)..."
uv run python after.py 2>&1 | tee captured/after.txt

echo ""
echo "Done. Captured output in ./captured/"
