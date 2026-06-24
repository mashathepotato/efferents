"""Lab-agnostic view over a run set.

Single source of truth for "what a run's columns mean": which is the headline
metric, which are configured panels, which are other (auto-discovered) columns,
and direction-aware best/improvement. Everything derives from the active
LabConfig.metrics plus the runs schema, so no consumer hardcodes domain column
names.
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from efferents import lab as _lab

META_COLUMNS = (
    "run_id", "started_at", "ended_at", "config_path",
    "campaign_id", "researcher_mode", "student_id",
    "git_commit", "duration_seconds",
)


def finite(x) -> float | None:
    """Return x as a float iff it is a finite real number, else None.
    bool is excluded; NaN/inf and non-numeric values return None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if math.isfinite(x) else None


def discover_columns(db_path, *, meta: tuple[str, ...] = META_COLUMNS) -> list[str]:
    """Non-meta columns present in the runs table (a lab's params + metrics).
    Missing db or missing table -> []."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(runs)")]
    except sqlite3.OperationalError:
        return []  # DB-level error (corruption/lock); safety net, not the missing-table case
    finally:
        conn.close()
    if not cols:  # no `runs` table -> PRAGMA yields no rows
        return []
    return [c for c in cols if c not in meta]


def headline():
    """The active lab's headline metric (column + direction)."""
    return _lab.get_config().metrics.headline


def panels():
    """The active lab's configured metric panels."""
    return _lab.get_config().metrics.panels


def headline_value(row: dict) -> float | None:
    """The finite headline-metric value of a run row, or None."""
    return finite(row.get(headline().column))


def best_run(rows: list[dict]) -> dict | None:
    """Best row by the headline column + direction, skipping rows whose headline
    value isn't finite. None if no scored rows."""
    h = headline()
    scored = [r for r in rows if finite(r.get(h.column)) is not None]
    if not scored:
        return None
    chooser = min if h.direction == "min" else max
    return chooser(scored, key=lambda r: finite(r.get(h.column)))


def improved(prev: float | None, current: float | None, *,
             direction: str, epsilon: float) -> bool:
    """True iff `current` improves on `prev` by more than epsilon in `direction`
    ('min' -> decrease, 'max' -> increase). prev None -> True when current is not
    None (first measurement counts as improvement)."""
    if current is None:
        return False
    if prev is None:
        return True
    return (prev - current) > epsilon if direction == "min" else (current - prev) > epsilon
