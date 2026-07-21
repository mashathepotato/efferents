"""Deterministic synthetic county records for the local climate-risk lab.

Each record is a small tabular feature vector (coastal flag, elevation,
historical storm rate, drainage index, population density) with a rare
high-risk label (~15% positive) derived from a noisy ground-truth risk score.
The class imbalance is the point: an adaptation-planning tool that misses
high-risk communities is useless, so the lab tunes the positive-class weight.

Stdlib-only, fixed seed. Real-data follow-up: FEMA National Risk Index and
NOAA Storm Events (both public CSV); this generator stands in for offline runs.
"""
from __future__ import annotations

import random

N_COUNTIES = 400
TRAIN_FRAC = 0.6
_SEED = 20260723

FEATURE_NAMES = ["coastal", "elevation", "storm_rate", "drainage", "pop_density"]


def make_dataset() -> tuple[list[list[float]], list[int], list[list[float]], list[int]]:
    """Returns (X_train, y_train, X_eval, y_eval)."""
    rng = random.Random(_SEED)
    X: list[list[float]] = []
    scores: list[float] = []
    for _ in range(N_COUNTIES):
        coastal = 1.0 if rng.random() < 0.3 else 0.0
        elevation = rng.uniform(0.0, 100.0)
        storm_rate = max(0.0, rng.gauss(3.0, 2.0))
        drainage = rng.uniform(0.0, 1.0)
        pop_density = rng.uniform(0.0, 10.0)
        X.append([coastal, elevation, storm_rate, drainage, pop_density])
        scores.append(
            2.2 * coastal
            - 0.030 * elevation
            + 0.55 * storm_rate
            - 1.2 * drainage
            + rng.gauss(0.0, 0.8)
        )

    # Threshold at the 85th percentile of the risk score -> ~15% positives.
    cut = sorted(scores)[int(0.85 * N_COUNTIES)]
    y = [1 if s > cut else 0 for s in scores]

    k = int(TRAIN_FRAC * N_COUNTIES)
    return X[:k], y[:k], X[k:], y[k:]
