"""Fit the forecast model and measure its attribution stability.

The swept knob is the ridge penalty. Training fits the full model, then
refits on B=20 bootstrap resamples and records how consistently the model
ranks feature importance (|standardized coefficient|) across refits — mean
pairwise Spearman correlation of the importance rankings. That stability
index is this lab's operationalization of "can a forecaster trust the
model's explanation," and it travels: any lab whose model exposes feature
importances can compute it.

Contract with efferents: last stdout line is {"checkpoint": "<path>"}.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import datagen
import ridge


def _load_flat_config(path: Path) -> dict:
    cfg: dict = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].rstrip()
        if not line or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        cfg[key.strip()] = raw.strip().strip("'\"")
    return cfg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = _load_flat_config(Path(args.config))
    lam = float(cfg.get("ridge_lambda", 10.0))
    n_boot = int(float(cfg.get("n_bootstrap", 20)))

    X_train, y_train, _, _ = datagen.make_dataset()
    scaler = ridge.Scaler(X_train, y_train)
    Xs = scaler.transform(X_train)
    yc = [v - scaler.y_mean for v in y_train]

    coefs = ridge.fit_ridge(Xs, yc, lam)

    rng = random.Random(7)
    n = len(Xs)
    rankings = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        bx = [Xs[i] for i in idx]
        by = [yc[i] for i in idx]
        bc = ridge.fit_ridge(bx, by, lam)
        rankings.append([abs(c) for c in bc])

    pairs, total = 0, 0.0
    for i in range(len(rankings)):
        for j in range(i + 1, len(rankings)):
            total += ridge.spearman(rankings[i], rankings[j])
            pairs += 1
    stability = total / pairs if pairs else 0.0

    ckpt_dir = Path(cfg.get("checkpoint_dir", "ckpt"))
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / "model.json"
    ckpt.write_text(json.dumps({
        "ridge_lambda": lam,
        "coefs": [round(c, 8) for c in coefs],
        "x_mean": scaler.x_mean,
        "x_std": scaler.x_std,
        "y_mean": scaler.y_mean,
        "attribution_stability": round(stability, 4),
        "feature_names": datagen.FEATURE_NAMES,
    }))
    print(json.dumps({"checkpoint": str(ckpt)}))


if __name__ == "__main__":
    main()
