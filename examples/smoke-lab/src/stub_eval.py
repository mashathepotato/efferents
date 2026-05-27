"""Trivial eval helper called from stub_run.py if needed."""
from __future__ import annotations


def loss(coefficient: float, noise: float = 0.0) -> float:
    return abs(0.8 - coefficient) + noise
