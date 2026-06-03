import sqlite3

from efferents.agents.researcher import _observed_metric_columns


def test_observed_metrics_excludes_meta(tmp_path):
    db = tmp_path / "runs.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT, started_at TEXT, campaign_id TEXT, "
        "seed INTEGER, config_yaml TEXT, synthetic_loss REAL)"
    )
    conn.commit()
    conn.close()
    cols = _observed_metric_columns(db)
    assert "synthetic_loss" in cols
    assert "run_id" not in cols


def test_observed_metrics_falls_back_to_primary_when_empty(tmp_path):
    # No runs table at all → discovery yields nothing → fall back to PRIMARY_METRICS.
    from efferents.agents.researcher import PRIMARY_METRICS
    db = tmp_path / "nope.sqlite"
    cols = _observed_metric_columns(db)
    assert list(cols) == list(PRIMARY_METRICS)
