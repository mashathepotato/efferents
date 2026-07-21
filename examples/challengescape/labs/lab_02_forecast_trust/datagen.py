"""Deterministic synthetic station-temperature data for the forecast-trust lab.

Daily temperature = seasonal cycle + AR(1) weather noise. The feature set
deliberately includes two near-duplicate (collinear) copies of the informative
lag features plus pure-noise distractors: with weak regularization, bootstrap
refits swap importance between collinear twins, which is exactly the
attribution instability that erodes forecaster trust in otherwise-accurate
models. Stdlib-only, fixed seed, byte-for-byte reproducible.

Real-data follow-up: station observations (e.g. NOAA GSOD) or a WeatherBench2
subset; this generator stands in so the lab runs offline.
"""
from __future__ import annotations

import math
import random

N_DAYS = 900
TRAIN_END = 600      # features/targets 2..599 train, 600..899 eval
_SEED = 20260722

FEATURE_NAMES = [
    "temp_lag1", "sin_doy", "cos_doy", "temp_lag2",
    "temp_lag1_dup", "temp_lag2_dup", "noise_a", "noise_b",
]


def make_dataset() -> tuple[list[list[float]], list[float], list[list[float]], list[float]]:
    """Returns (X_train, y_train, X_eval, y_eval)."""
    rng = random.Random(_SEED)
    w = 0.0
    temps: list[float] = []
    for t in range(N_DAYS):
        w = 0.7 * w + rng.gauss(0.0, 2.0)
        temps.append(15.0 + 10.0 * math.sin(2 * math.pi * t / 365.25) + w)

    X: list[list[float]] = []
    y: list[float] = []
    for t in range(2, N_DAYS):
        row = [
            temps[t - 1],
            math.sin(2 * math.pi * t / 365.25),
            math.cos(2 * math.pi * t / 365.25),
            temps[t - 2],
            temps[t - 1] + rng.gauss(0.0, 0.05),
            temps[t - 2] + rng.gauss(0.0, 0.05),
            rng.gauss(0.0, 1.0),
            rng.gauss(0.0, 1.0),
        ]
        X.append(row)
        y.append(temps[t])

    k = TRAIN_END - 2
    return X[:k], y[:k], X[k:], y[k:]
