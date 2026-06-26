"""Toy 'training' script for the efferents repo-adapter example.

Trains a 1-D logistic-regression classifier on a fixed, deterministic synthetic
dataset with plain-Python gradient descent (no numpy, no GPU), then writes a
checkpoint. The decision `threshold` is read from the config and passed through
to the checkpoint so the evaluation can apply it — this is the knob the lab
sweeps (classification-threshold tuning on an imbalanced validation set).

Contract with efferents: the LAST line on stdout is a JSON object naming the
checkpoint it wrote, e.g. {"checkpoint": "ckpt/model.json"}.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

# Fixed synthetic training set: (feature, label), label follows feature > 0
# with a little boundary noise.
_TRAIN = [(-3.0, 0), (-2.0, 0), (-1.2, 0), (-0.4, 1), (-0.1, 0),
          (0.1, 1), (0.4, 0), (1.2, 1), (2.0, 1), (3.0, 1)]


def _load_flat_config(path: Path) -> dict:
    """Tiny YAML-subset reader for flat `key: value` configs — keeps this
    example runnable under any python3 with no pip dependencies."""
    cfg: dict = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].rstrip()
        if not line or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        val = raw.strip()
        try:
            cfg[key.strip()] = int(val)
        except ValueError:
            try:
                cfg[key.strip()] = float(val)
            except ValueError:
                cfg[key.strip()] = val
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
    lr = float(cfg.get("learning_rate", 0.3))
    epochs = int(cfg.get("epochs", 200))
    threshold = float(cfg.get("threshold", 0.5))

    w, b = 0.0, 0.0
    for _ in range(epochs):
        gw = gb = 0.0
        for x, y in _TRAIN:
            err = _sigmoid(w * x + b) - y
            gw += err * x
            gb += err
        n = len(_TRAIN)
        w -= lr * gw / n
        b -= lr * gb / n

    ckpt_dir = Path(cfg.get("checkpoint_dir", "ckpt"))
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / "model.json"
    ckpt.write_text(json.dumps({"w": w, "b": b, "threshold": threshold}))

    print(json.dumps({"checkpoint": str(ckpt)}))


if __name__ == "__main__":
    main()
