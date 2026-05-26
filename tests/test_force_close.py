"""Orchestrator closes campaigns with no new runs in 48h."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from efferents.agents.orchestrator import close_stale_campaigns
from efferents.agents.state import (
    campaign_insert,
    campaign_open_list,
    init_lab,
    lab_paths,
)
from efferents.migrations.runner import apply_campaigns_migration


@pytest.fixture
def paths(tmp_lab):
    p = lab_paths(tmp_lab)
    init_lab(p)
    import sqlite3
    conn = sqlite3.connect(p.runs_db)
    conn.executescript(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL,"
        " config_yaml TEXT NOT NULL, config_hash TEXT NOT NULL);"
    )
    conn.commit()
    conn.close()
    apply_campaigns_migration(p.runs_db)
    return p


def test_close_stale_closes_old_campaign(paths):
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
    campaign_insert(
        paths.runs_db,
        id="old",
        lab_id="qfm-diffusion",
        question="q",
        hypothesis_path="popper-corpus/old/hypothesis.md",
        hypothesis_hash="sha256:" + "0" * 64,
        opened_at=long_ago,
    )
    closed = close_stale_campaigns(paths.runs_db, lab_id="qfm-diffusion", hours=48)
    assert closed == ["old"]
    assert campaign_open_list(paths.runs_db, "qfm-diffusion") == []


def test_close_stale_leaves_fresh_alone(paths):
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    campaign_insert(
        paths.runs_db,
        id="fresh",
        lab_id="qfm-diffusion",
        question="q",
        hypothesis_path="popper-corpus/fresh/hypothesis.md",
        hypothesis_hash="sha256:" + "0" * 64,
        opened_at=recent,
    )
    assert close_stale_campaigns(paths.runs_db, lab_id="qfm-diffusion", hours=48) == []
    assert len(campaign_open_list(paths.runs_db, "qfm-diffusion")) == 1
