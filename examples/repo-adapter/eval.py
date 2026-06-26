"""Toy 'evaluation' script for the efferents repo-adapter example.

Loads a checkpoint written by train.py and computes val_f1 on a fixed,
deterministic, imbalanced validation set using the checkpoint's decision
threshold. f1 has a clean interior optimum in the threshold, so sweeping it is a
real (if tiny) tuning problem.

Emits the metric as a trailing JSON line: {"metrics": {"val_f1": 0.8889}}.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

# Held-out, class-imbalanced validation set: (feature, label).
_VAL = [(0.5, 1), (0.9, 1), (1.5, 1), (2.5, 1),
        (-2.5, 0), (-1.5, 0), (-1.0, 0), (-0.6, 0), (-0.2, 0), (0.3, 0), (0.6, 0)]


def _sigmoid(z: float) -> float:
    if z < -30:
        return 0.0
    if z > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def _f1(preds: list[int], labels: list[int]) -> float:
    tp = sum(1 for p, y in zip(preds, labels) if p == 1 and y == 1)
    fp = sum(1 for p, y in zip(preds, labels) if p == 1 and y == 0)
    fn = sum(1 for p, y in zip(preds, labels) if p == 0 and y == 1)
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    args = ap.parse_args()

    model = json.loads(Path(args.checkpoint).read_text())
    w, b, tau = model.get("w"), model.get("b"), float(model.get("threshold", 0.5))

    if w is None or b is None or not (math.isfinite(w) and math.isfinite(b)):
        print(json.dumps({"metrics": {"val_f1": 0.0}}))
        return

    preds = [1 if _sigmoid(w * x + b) >= tau else 0 for x, _ in _VAL]
    labels = [y for _, y in _VAL]
    val_f1 = round(_f1(preds, labels), 4)
    print(json.dumps({"metrics": {"val_f1": val_f1}}))


if __name__ == "__main__":
    main()
