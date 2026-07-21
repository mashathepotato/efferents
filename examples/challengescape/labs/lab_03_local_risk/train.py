"""Fit a weighted logistic-regression county-risk classifier.

The swept knob is the positive-class weight: high-risk counties are ~15% of
records, so an unweighted fit optimizes accuracy by under-flagging them, and
an over-weighted fit floods planners with false alarms. Plain-Python gradient
descent on standardized features — no dependencies, deterministic.

Contract with efferents: last stdout line is {"checkpoint": "<path>"}.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import datagen


def _load_flat_config(path: Path) -> dict:
    cfg: dict = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].rstrip()
        if not line or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        cfg[key.strip()] = raw.strip().strip("'\"")
    return cfg


def _sigmoid(z: float) -> float:
    if z < -30:
        return 0.0
    if z > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = _load_flat_config(Path(args.config))
    pos_weight = float(cfg.get("pos_weight", 1.0))
    lr = float(cfg.get("learning_rate", 0.5))
    epochs = int(float(cfg.get("epochs", 400)))

    X_train, y_train, _, _ = datagen.make_dataset()
    d = len(X_train[0])
    n = len(X_train)

    means = [sum(r[j] for r in X_train) / n for j in range(d)]
    stds = []
    for j in range(d):
        var = sum((r[j] - means[j]) ** 2 for r in X_train) / n
        stds.append(var ** 0.5 or 1.0)
    Xs = [[(r[j] - means[j]) / stds[j] for j in range(d)] for r in X_train]

    w = [0.0] * d
    b = 0.0
    for _ in range(epochs):
        gw = [0.0] * d
        gb = 0.0
        for row, y in zip(Xs, y_train):
            z = sum(wj * xj for wj, xj in zip(w, row)) + b
            err = _sigmoid(z) - y
            weight = pos_weight if y == 1 else 1.0
            for j in range(d):
                gw[j] += weight * err * row[j]
            gb += weight * err
        for j in range(d):
            w[j] -= lr * gw[j] / n
        b -= lr * gb / n

    ckpt_dir = Path(cfg.get("checkpoint_dir", "ckpt"))
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / "model.json"
    ckpt.write_text(json.dumps({
        "pos_weight": pos_weight,
        "coefs": [round(v, 8) for v in w],
        "intercept": round(b, 8),
        "x_mean": means,
        "x_std": stds,
        "feature_names": datagen.FEATURE_NAMES,
    }))
    print(json.dumps({"checkpoint": str(ckpt)}))


if __name__ == "__main__":
    main()
