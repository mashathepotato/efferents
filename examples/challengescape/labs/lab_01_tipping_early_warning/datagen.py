"""Deterministic synthetic time series for the tipping-point early-warning lab.

Generates an ensemble of AR(1) series exhibiting critical slowing down: in
"transitioning" series the autoregressive coefficient phi ramps toward 1 ahead
of a known transition time T_C, which is the classic early-warning signature
(rising lag-1 autocorrelation and variance). "Control" series keep phi fixed.

Everything is seeded and stdlib-only so runs are byte-for-byte reproducible.
The real-data follow-up for this challenge is public AMOC / RAPID-array and
paleoclimate records; this generator stands in so the lab runs offline.
"""
from __future__ import annotations

import random

LENGTH = 500
T_C = 400          # transition time in transitioning series
RAMP_START = 100   # phi starts drifting here
PHI_BASE = 0.5
PHI_END = 0.98
NOISE_SD = 1.0

N_CONTROL = 20
N_TRANS = 20
_SEED = 20260721


def _ar1(rng: random.Random, phi_at) -> list[float]:
    x = 0.0
    out = []
    for t in range(LENGTH):
        x = phi_at(t) * x + rng.gauss(0.0, NOISE_SD)
        out.append(x)
    return out


def make_ensemble() -> dict:
    """Returns {"control": [...], "transitioning": [...]} lists of series."""
    rng = random.Random(_SEED)

    def ramp(t: int) -> float:
        if t < RAMP_START:
            return PHI_BASE
        if t >= T_C:
            return PHI_END
        frac = (t - RAMP_START) / (T_C - RAMP_START)
        return PHI_BASE + frac * (PHI_END - PHI_BASE)

    control = [_ar1(rng, lambda t: PHI_BASE) for _ in range(N_CONTROL)]
    trans = [_ar1(rng, ramp) for _ in range(N_TRANS)]
    return {"control": control, "transitioning": trans}


def split(series: list, train_frac: float = 0.5) -> tuple[list, list]:
    k = int(len(series) * train_frac)
    return series[:k], series[k:]


def rolling_ac1(x: list[float], window: int) -> list[tuple[int, float]]:
    """(t, lag-1 autocorrelation of x[t-window:t]) for each t >= window."""
    out = []
    for t in range(window, len(x)):
        seg = x[t - window:t]
        n = len(seg)
        mean = sum(seg) / n
        var = sum((v - mean) ** 2 for v in seg)
        if var <= 1e-12:
            out.append((t, 0.0))
            continue
        cov = sum((seg[i] - mean) * (seg[i + 1] - mean) for i in range(n - 1))
        out.append((t, cov / var))
    return out
