"""Tiny .env loader (no python-dotenv dependency). KEY=VALUE per line.

.env values OVERRIDE existing env vars — per-project keys win over shell-wide
settings. This is intentional: the project's .env is the source of truth for
the agent loop's spend.

Shared by both entry points:
  - efferents.cli (the `efferents start` deployment path)
  - efferents.agents.__main__ (the legacy `python -m efferents.agents` path)
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip('"').strip("'")
