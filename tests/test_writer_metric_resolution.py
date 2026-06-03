from efferents.agents.writer import _best_metric, _resolve_campaign_metric


def test_best_metric_min():
    rows = [{"loss": 0.5}, {"loss": 0.2}, {"loss": None}, {}]
    assert _best_metric(rows, "loss", "min") == 0.2


def test_best_metric_max():
    rows = [{"acc": 0.5}, {"acc": 0.9}, {"acc": None}]
    assert _best_metric(rows, "acc", "max") == 0.9


def test_best_metric_absent_column_returns_none():
    rows = [{"other": 1.0}, {}]
    assert _best_metric(rows, "loss", "min") is None


def test_resolve_campaign_metric_prefers_campaign():
    campaign = {"headline_metric": "synthetic_loss", "headline_direction": "min"}
    assert _resolve_campaign_metric(campaign, default=("e_w1", "min")) == ("synthetic_loss", "min")


def test_resolve_campaign_metric_falls_back_when_null():
    campaign = {"headline_metric": None, "headline_direction": None}
    assert _resolve_campaign_metric(campaign, default=("e_w1", "min")) == ("e_w1", "min")


import sqlite3
from pathlib import Path


def _seed_runs(db: Path, campaign_id: str, metric: str, vals: list[float]):
    conn = sqlite3.connect(db)
    conn.execute(
        f"CREATE TABLE runs (run_id TEXT, started_at TEXT, campaign_id TEXT, "
        f"seed INTEGER, {metric} REAL)"
    )
    for i, v in enumerate(vals):
        conn.execute(
            "INSERT INTO runs (run_id, started_at, campaign_id, seed, " + metric + ") "
            "VALUES (?, ?, ?, ?, ?)",
            (f"r{i}", "2026-01-01T00:00:00+00:00", campaign_id, 0, v),
        )
    conn.commit()
    conn.close()


def test_best_metric_reads_campaign_runs(tmp_path):
    db = tmp_path / "runs.sqlite"
    _seed_runs(db, "c1", "synthetic_loss", [0.4, 0.1, 0.3])
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM runs WHERE campaign_id='c1'")]
    conn.close()
    assert _best_metric(rows, "synthetic_loss", "min") == 0.1
