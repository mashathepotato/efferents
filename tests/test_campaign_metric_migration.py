import sqlite3

from efferents.migrations.runner import apply_campaigns_migration


def _columns(db_path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(campaigns)")}
    finally:
        conn.close()


def test_migration_adds_metric_columns(tmp_path):
    db = tmp_path / "runs.sqlite"
    apply_campaigns_migration(db)
    cols = _columns(db)
    assert "headline_metric" in cols
    assert "headline_direction" in cols


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "runs.sqlite"
    apply_campaigns_migration(db)
    apply_campaigns_migration(db)  # must not raise "duplicate column"
    cols = _columns(db)
    assert "headline_metric" in cols
    assert "headline_direction" in cols
