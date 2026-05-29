"""Shared pytest fixtures."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def tmp_lab(tmp_path: Path) -> Path:
    """Empty lab/ directory with subdirs created."""
    (tmp_path / "digests").mkdir()
    (tmp_path / "knowledge").mkdir()
    return tmp_path


@pytest.fixture
def fresh_runs_db(tmp_lab: Path) -> Path:
    """SQLite file with a runs table matching the current production schema
    BEFORE migration. Used to test migration idempotency."""
    db = tmp_lab / "runs.sqlite"
    conn = sqlite3.connect(db)
    # Snapshot of production schema BEFORE the 2026-05-17 campaigns migration.
    # Do NOT add campaign_id / researcher_mode here — those columns are what
    # the migration test will verify. Source of truth: auto_qml/run.py RUNS_SCHEMA.
    conn.executescript(
        """
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            config_path TEXT,
            config_yaml TEXT NOT NULL,
            config_hash TEXT NOT NULL,
            seed INTEGER,
            model TEXT,
            raw_q INTEGER,
            raw_px INTEGER,
            epochs INTEGER,
            aug_depth INTEGER,
            aug_shared_unitary INTEGER,
            cond_drop_p REAL,
            eval_kind TEXT,
            eval_n INTEGER,
            val_x0_mse REAL,
            e_w1 REAL,
            active_frac_w1 REAL,
            radial_l2 REAL,
            radial_l2_log REAL,
            gen_max_to_real_max REAL,
            duration_seconds REAL,
            notes TEXT,
            git_commit TEXT,
            samples_png TEXT,
            lit_context_json TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return db


class FakeAnthropicResponse:
    """Mimics anthropic.types.Message just enough for our consumers."""

    # Default token counts are non-zero so cost paths run in tests.
    # Pass input_tokens=0, output_tokens=0 in budget-threshold tests to avoid
    # tripping BudgetTracker.should_pause() unintentionally.
    def __init__(self, text: str, *, input_tokens: int = 1000, output_tokens: int = 200,
                 cache_creation: int = 0, cache_read: int = 0):
        self.content = [type("Block", (), {"text": text, "type": "text"})()]
        self.usage = type(
            "Usage",
            (),
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            },
        )()
        self.stop_reason = "end_turn"


class FakeAnthropic:
    """Stand-in for anthropic.Anthropic.

    Construct with a list of canned response texts; .messages.create() pops
    them in order. Records every call for inspection.
    """

    def __init__(self, responses: list[str], **_kwargs: Any):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = self  # so client.messages.create(...) works

    def create(self, **kwargs: Any) -> FakeAnthropicResponse:
        self.calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("FakeAnthropic ran out of canned responses")
        return FakeAnthropicResponse(self._responses.pop(0))


@pytest.fixture
def fake_anthropic_factory():
    """Returns a function that builds a FakeAnthropic from a list of strings."""
    return lambda responses: FakeAnthropic(responses)


@pytest.fixture(autouse=True)
def smoke_lab_config(tmp_path_factory):
    """Auto-install a minimal LabConfig for every test, then tear down.

    Tests that need a custom LabConfig can call lab.set_config(...) themselves
    inside the test body; this fixture's teardown still clears it.
    """
    from efferents import lab as lab_mod
    from efferents.lab import (
        Budget, Executor, Headline, LabConfig, Metrics, Panel, Source,
    )

    tmp = tmp_path_factory.mktemp("smoke-lab-fixture")
    src_dir = tmp / "src"
    src_dir.mkdir()
    (src_dir / "default.yaml").touch()

    cfg = LabConfig(
        lab_id="smoke-fixture",
        domain="test",
        pi_handle=None,
        source=Source(dir=src_dir),
        executor=Executor(
            run_command="echo {config_path}",
            smoke_command=None,
            config_template=src_dir / "default.yaml",
        ),
        metrics=Metrics(
            headline=Headline(column="synthetic_loss", direction="min"),
            panels=(Panel(column="synthetic_loss", label="Loss"),),
        ),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    # Provision lab/runs.sqlite with the smoke schema so persistence-touching
    # tests don't have to bootstrap it themselves.
    import os
    lab_dir = tmp / "lab"
    lab_dir.mkdir(exist_ok=True)
    from efferents.migrations.runner import ensure_runs_table
    ensure_runs_table(lab_dir / "state.db", cfg)
    # Chdir so relative "lab/runs.sqlite" lookups in _persist_run_result resolve.
    prev_cwd = os.getcwd()
    os.chdir(tmp)
    try:
        yield cfg
    finally:
        os.chdir(prev_cwd)
        lab_mod._active = None
