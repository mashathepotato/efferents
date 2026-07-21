"""Score the county-risk classifier on held-out counties.

Headline metric: F1 on the high-risk class at the 0.5 probability cutoff —
the class planners actually act on. Precision and recall are reported
separately so reviewers can see which side of the tradeoff a weight buys.

Emits a trailing JSON line: {"metrics": {"f1_high_risk": ...}}.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import datagen


def _sigmoid(z: float) -> float:
    if z < -30:
        return 0.0
    if z > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    args = ap.parse_args()
    model = json.loads(Path(args.checkpoint).read_text())
    w, b = model["coefs"], model["intercept"]
    means, stds = model["x_mean"], model["x_std"]

    _, _, X_eval, y_eval = datagen.make_dataset()
    preds = []
    for row in X_eval:
        z = sum(
            wj * (v - m) / s for wj, v, m, s in zip(w, row, means, stds)
        ) + b
        preds.append(1 if _sigmoid(z) >= 0.5 else 0)

    tp = sum(1 for p, y in zip(preds, y_eval) if p == 1 and y == 1)
    fp = sum(1 for p, y in zip(preds, y_eval) if p == 1 and y == 0)
    fn = sum(1 for p, y in zip(preds, y_eval) if p == 0 and y == 1)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0

    print(json.dumps({"metrics": {
        "f1_high_risk": round(f1, 4),
        "precision_high_risk": round(precision, 4),
        "recall_high_risk": round(recall, 4),
        "n_flagged": tp + fp,
        "n_high_risk_true": tp + fn,
    }}))


if __name__ == "__main__":
    main()
