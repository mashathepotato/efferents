"""'Training' = selecting the verification configuration under test.

The swept knob is board_size k: how many of the five recorded fresh-context
reviewers sit on the board. All reasoning verdicts were recorded at build
time (safety_lab.py verdicts); train just pins the configuration so eval can
score it deterministically.

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
    board_size = int(float(cfg.get("board_size", 3)))

    ckpt_dir = Path(cfg.get("checkpoint_dir", "ckpt"))
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / "config.json"
    ckpt.write_text(json.dumps({"board_size": board_size}))
    print(json.dumps({"checkpoint": str(ckpt)}))


if __name__ == "__main__":
    main()
