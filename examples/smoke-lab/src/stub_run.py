"""Smoke-lab "training" run: reads config, computes synthetic_loss, emits stdout JSON.

Hypothesis under test: "increasing coefficient above 0.7 reduces synthetic_loss below 0.1".
Truth: synthetic_loss = abs(0.8 - coefficient) + small_noise.

This is a stub for proving the efferents framework plumbing — NOT real research.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
import uuid

import yaml


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=2
        ).strip()
    except Exception:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    cfg = yaml.safe_load(open(args.config))
    coefficient = float(cfg.get("coefficient", 0.5))
    seed = int(cfg.get("seed", 42))
    rng = random.Random(seed)

    start = time.time()
    noise = rng.gauss(0, 0.01) if not args.smoke else 0.0
    synthetic_loss = abs(0.8 - coefficient) + noise

    payload = {
        "run_id": str(uuid.uuid4()),
        "metrics": {"synthetic_loss": synthetic_loss},
        "git_commit": _git_commit(),
        "elapsed_s": time.time() - start,
        "artifacts": [],
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
