#!/usr/bin/env bash
# Relaunch all three Challengescape labs and rebuild the shared journal.
# Fully offline and deterministic: no API key, no network. Run from the
# efferents repo root with the project venv built (see repo README).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
EFF="$REPO_ROOT/.venv/bin/efferents"
PY="$REPO_ROOT/.venv/bin/python"

for lab in "$HERE"/labs/*/; do
  name="$(basename "$lab")"
  echo "=== $name ==="
  "$EFF" run "$lab" --approve --out "$lab/out"
done

"$PY" "$HERE/crosslab.py"
echo
echo "Shared journal: $HERE/shared_journal/index.md"
echo "Note: reruns regenerate journal entries 001-004 per lab. The review"
echo "layer (005_review.md, 006_next_experiment_v2.md, shared_journal/reviews/)"
echo "is the recorded LLM review pass and is not overwritten by this script."
