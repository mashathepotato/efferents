import sqlite3
from pathlib import Path

from efferents.dashboard import reader


def _make_runs_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, "
        "ended_at TEXT, synthetic_loss REAL)"
    )
    conn.executemany(
        "INSERT INTO runs (run_id, started_at, synthetic_loss) VALUES (?, ?, ?)",
        [("r1", "2026-06-01T10:00:00", 0.08),
         ("r2", "2026-06-01T10:01:00", 0.05),
         ("r3", "2026-06-01T10:02:00", 0.03)],
    )
    conn.commit()
    conn.close()


def test_read_state_stopped_when_no_pidfile(tmp_path, smoke_lab_config):
    state = reader.read_state(tmp_path)
    assert state["lab_id"] == "smoke-fixture"
    assert state["status"] == "stopped"
    assert state["budget"]["spent"] == 0.0
    assert "cap" in state["budget"]


def test_read_state_budget_sums_cost(tmp_path, smoke_lab_config):
    (tmp_path / "budget.jsonl").write_text(
        '{"cost_usd": 0.01}\n{"cost_usd": 0.02}\n'
    )
    state = reader.read_state(tmp_path)
    assert abs(state["budget"]["spent"] - 0.03) < 1e-9


def test_read_runs_returns_headline_and_series(tmp_path, smoke_lab_config):
    _make_runs_db(tmp_path / "runs.sqlite")
    out = reader.read_runs(tmp_path)
    assert out["headline"] == {"column": "synthetic_loss", "direction": "min"}
    assert [r["run_id"] for r in out["runs"]] == ["r3", "r2", "r1"]  # newest first
    assert [pt["value"] for pt in out["series"]] == [0.08, 0.05, 0.03]  # oldest->newest


def test_read_runs_empty_when_no_db(tmp_path, smoke_lab_config):
    out = reader.read_runs(tmp_path)
    assert out["runs"] == []
    assert out["series"] == []
    assert out["headline"]["column"] == "synthetic_loss"


def test_read_papers_reads_paper_dir(tmp_path, smoke_lab_config):
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "camp-1.md").write_text(
        "---\nlab_id: smoke-fixture\ncampaign_id: camp-1\n"
        "novelty_claim: A real finding.\npublished_at: 2026-06-09\n"
        "status: preprint\n---\n\n# Title\n\nbody\n"
    )
    papers = reader.read_papers(tmp_path)
    assert len(papers) == 1
    assert papers[0]["campaign_id"] == "camp-1"
    assert papers[0]["title"] == "Title"


def test_read_papers_empty_when_no_dir(tmp_path, smoke_lab_config):
    assert reader.read_papers(tmp_path) == []


def test_read_activity_parses_notebook(tmp_path, smoke_lab_config):
    (tmp_path / "lab_notebook.md").write_text(
        "## 2026-06-01T10:00:00+00:00 — orchestrator start\n\n"
        "efferents daemon\n\n"
        "## 2026-06-01T10:05:00+00:00 — Researcher mode: refine\n\n"
        "proposed 4 configs\n\n"
    )
    acts = reader.read_activity(tmp_path)
    assert acts[0]["title"] == "Researcher mode: refine"  # newest first
    assert acts[1]["title"] == "orchestrator start"


def test_read_activity_empty_when_no_notebook(tmp_path, smoke_lab_config):
    assert reader.read_activity(tmp_path) == []


def test_read_papers_reads_plural_papers_dir(tmp_path, smoke_lab_config):
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()
    (papers_dir / "camp-2.md").write_text(
        "---\nlab_id: smoke-fixture\ncampaign_id: camp-2\n"
        "novelty_claim: Another finding.\npublished_at: 2026-06-10\n"
        "status: preprint\n---\n\n# T2\n\nbody\n"
    )
    papers = reader.read_papers(tmp_path)
    assert [p["campaign_id"] for p in papers] == ["camp-2"]


def test_read_activity_ignores_notebook_preamble(tmp_path, smoke_lab_config):
    (tmp_path / "lab_notebook.md").write_text(
        "# Lab notebook\n\nAgent-only, append-only narrative.\n\n"
        "Initialized 2026-06-01T09:00:00+00:00.\n\n"
        "## 2026-06-01T10:00:00+00:00 — orchestrator start\n\nefferents daemon\n\n"
    )
    acts = reader.read_activity(tmp_path)
    assert len(acts) == 1
    assert acts[0]["title"] == "orchestrator start"
