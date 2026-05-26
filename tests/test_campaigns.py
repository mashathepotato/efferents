"""Campaign CRUD + cap + force-close helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from efferents.agents.state import (
    campaign_close,
    campaign_insert,
    campaign_open_list,
    campaign_stale_open,
)
from efferents.migrations.runner import apply_campaigns_migration


@pytest.fixture
def db(fresh_runs_db):
    apply_campaigns_migration(fresh_runs_db)
    return fresh_runs_db


def _row(lab_id="qfm-diffusion", id_="c1", question="does X improve W1?"):
    return {
        "id": id_,
        "lab_id": lab_id,
        "question": question,
        "hypothesis_path": f"popper-corpus/{id_}/hypothesis.md",
        "hypothesis_hash": "sha256:" + ("0" * 64),
    }


def test_insert_and_list_open(db):
    campaign_insert(db, **_row(id_="c1"))
    campaign_insert(db, **_row(id_="c2"))
    opens = campaign_open_list(db, "qfm-diffusion")
    assert {c["id"] for c in opens} == {"c1", "c2"}


def test_close_excludes_from_open_list(db):
    campaign_insert(db, **_row(id_="c1"))
    campaign_close(db, "c1", reason="resolved")
    assert campaign_open_list(db, "qfm-diffusion") == []


def test_cap_enforced_by_caller_not_db(db):
    # campaign_insert does NOT enforce the cap; the caller does.
    campaign_insert(db, **_row(id_="c1"))
    campaign_insert(db, **_row(id_="c2"))
    campaign_insert(db, **_row(id_="c3"))
    assert len(campaign_open_list(db, "qfm-diffusion")) == 3


def test_stale_open_returns_campaigns_with_no_runs_past_threshold(db):
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    campaign_insert(db, **_row(id_="old"), opened_at=long_ago)
    campaign_insert(db, **_row(id_="fresh"), opened_at=recent)

    stale = campaign_stale_open(db, "qfm-diffusion", hours=48)
    assert {c["id"] for c in stale} == {"old"}


def test_stale_open_respects_recent_runs(db):
    """A campaign with an old opened_at but a recent run is NOT stale."""
    import sqlite3
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    recent_run = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    campaign_insert(db, **_row(id_="old-but-active"), opened_at=long_ago)

    # Insert a recent run tagged to this campaign
    conn = sqlite3.connect(db)
    conn.execute(
        """INSERT INTO runs(run_id, started_at, config_yaml, config_hash, campaign_id)
           VALUES (?, ?, ?, ?, ?)""",
        ("r1", recent_run, "yaml", "hash", "old-but-active"),
    )
    conn.commit()
    conn.close()

    stale = campaign_stale_open(db, "qfm-diffusion", hours=48)
    assert stale == []
