"""Calibrate a tipping-point early-warning detector on control series.

The swept knob is the rolling-window length used to estimate lag-1
autocorrelation. "Training" = choosing the alarm threshold that holds the
series-level false-alarm rate on control (non-transitioning) series to ~5%:
the threshold is the 95th percentile of each control series' maximum rolling
autocorrelation. Short windows are noisy (high thresholds, late alarms);
long windows lag the drift (also late alarms) — the tradeoff the lab probes.

Contract with efferents: last stdout line is {"checkpoint": "<path>"}.
"""
from __future__ import annotations

import argparse
import json
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


def _percentile(values: list[float], q: float) -> float:
    vals = sorted(values)
    if not vals:
        return 0.0
    idx = q * (len(vals) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = _load_flat_config(Path(args.config))
    window = int(float(cfg.get("window", 50)))

    ensemble = datagen.make_ensemble()
    control_train, _ = datagen.split(ensemble["control"])

    maxima = []
    for series in control_train:
        ac = datagen.rolling_ac1(series, window)
        maxima.append(max(v for _, v in ac) if ac else 0.0)
    threshold = _percentile(maxima, 0.95)

    ckpt_dir = Path(cfg.get("checkpoint_dir", "ckpt"))
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / "detector.json"
    ckpt.write_text(json.dumps({"window": window, "threshold": round(threshold, 6)}))
    print(json.dumps({"checkpoint": str(ckpt)}))


if __name__ == "__main__":
    main()
