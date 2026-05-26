"""Migration runner must be idempotent and add the right columns."""
from __future__ import annotations

import sqlite3


from efferents.migrations.runner import apply_campaigns_migration


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()


def test_migration_adds_campaigns_table(fresh_runs_db):
    apply_campaigns_migration(fresh_runs_db)
    assert "campaigns" in _tables(fresh_runs_db)


def test_migration_adds_new_runs_columns(fresh_runs_db):
    apply_campaigns_migration(fresh_runs_db)
    cols = _columns(fresh_runs_db, "runs")
    assert "campaign_id" in cols
    assert "researcher_mode" in cols


def test_migration_is_idempotent(fresh_runs_db):
    apply_campaigns_migration(fresh_runs_db)
    apply_campaigns_migration(fresh_runs_db)  # must not raise


def test_migration_preserves_existing_rows(fresh_runs_db):
    conn = sqlite3.connect(fresh_runs_db)
    conn.execute(
        """INSERT INTO runs(run_id, started_at, config_yaml, config_hash)
           VALUES (?, ?, ?, ?)""",
        ("r1", "2026-05-01T00:00:00Z", "model: qfm", "deadbeef"),
    )
    conn.commit()
    conn.close()

    apply_campaigns_migration(fresh_runs_db)

    conn = sqlite3.connect(fresh_runs_db)
    row = conn.execute(
        "SELECT run_id, campaign_id, researcher_mode FROM runs WHERE run_id = ?",
        ("r1",),
    ).fetchone()
    conn.close()
    assert row == ("r1", None, None)
