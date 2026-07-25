"""'Training' = selecting the verification configuration under test.

The swept knob is pool_n: how many of the five recorded fresh-context
reviewers must flag a module for the board to convict. All reasoning
verdicts were recorded at build time (cycle2.py verdicts); train just pins
the configuration so eval can score it deterministically.

Contract with efferents: last stdout line is {"checkpoint": "<path>"}.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


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
    pool_n = int(float(cfg.get("pool_n", 3)))

    ckpt_dir = Path(cfg.get("checkpoint_dir", "ckpt"))
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / "config.json"
    ckpt.write_text(json.dumps({"pool_n": pool_n}))
    print(json.dumps({"checkpoint": str(ckpt)}))


if __name__ == "__main__":
    main()
