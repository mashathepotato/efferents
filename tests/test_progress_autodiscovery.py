import sqlite3

from efferents.agents.progress import _discover_metric_columns

_META = {
    "run_id", "started_at", "ended_at", "config_path", "campaign_id",
    "researcher_mode", "student_id", "git_commit", "duration_seconds", "seed",
    "config_yaml", "eval_kind",
}


def test_discovers_non_meta_real_columns(tmp_path):
    db = tmp_path / "runs.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT, started_at TEXT, campaign_id TEXT, "
        "seed INTEGER, synthetic_loss REAL, extra_metric REAL)"
    )
    conn.commit()
    conn.close()
    found = _discover_metric_columns(db, meta=_META)
    assert "synthetic_loss" in found
    assert "extra_metric" in found
    assert "run_id" not in found
    assert "campaign_id" not in found


def test_missing_db_returns_empty(tmp_path):
    assert _discover_metric_columns(tmp_path / "nope.sqlite") == []
