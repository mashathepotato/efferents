"""Minimal smoke tests for the progress dashboard.

Avoid testing matplotlib rendering output (expensive, brittle). Instead test
that:
- write_progress produces an HTML file on a pre-migration DB (graceful fallback)
- write_progress includes expected markers when campaigns + runs exist
- The 'sample-eval only' filter excludes recon rows from headlines
"""
from __future__ import annotations

import sqlite3

import pytest

from efferents.agents.progress import write_progress
from efferents.agents.state import init_lab, lab_paths
from efferents.migrations.runner import apply_campaigns_migration
from efferents import lab as lab_mod
from efferents.lab import Budget, Executor, Headline, LabConfig, Metrics, Panel, Source


def _insert_run(conn, **kw):
    cols = list(kw.keys())
    placeholders = ",".join(["?"] * len(cols))
    conn.execute(
        f"INSERT INTO runs({','.join(cols)}) VALUES ({placeholders})",
        tuple(kw.values()),
    )


@pytest.fixture
def lab_with_db(tmp_lab):
    paths = lab_paths(tmp_lab)
    init_lab(paths)
    conn = sqlite3.connect(paths.runs_db)
    conn.executescript(
        """
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL,
            config_yaml TEXT NOT NULL, config_hash TEXT NOT NULL,
            seed INTEGER, model TEXT, raw_q INTEGER, epochs INTEGER,
            aug_depth INTEGER, eval_kind TEXT, e_w1 REAL,
            val_x0_mse REAL, active_frac_w1 REAL, radial_l2_log REAL,
            gen_max_to_real_max REAL, samples_png TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return paths


def test_pre_migration_db_renders_fallback(lab_with_db):
    """No campaigns table → falls back to flat run view without crashing."""
    out = write_progress(lab_with_db)
    assert out.exists()
    html = out.read_text()
    assert "qfm-diffusion" in html
    assert "no campaigns opened yet" in html


def test_no_runs_renders_empty_states(lab_with_db):
    apply_campaigns_migration(lab_with_db.runs_db)
    out = write_progress(lab_with_db)
    html = out.read_text()
    assert "0 runs" in html
    assert "no scored runs yet" in html


def test_best_of_each_metric_in_header(lab_with_db, tmp_path):
    """Header line shows best across multiple metrics drawn from LabConfig panels."""
    # Configure a LabConfig with four QML-like panels to verify multi-metric rendering.
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.yaml").touch()
    cfg = LabConfig(
        lab_id="qfm-diffusion", domain="quantum", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command="echo {config_path}", smoke_command=None,
            config_template=src / "c.yaml",
        ),
        metrics=Metrics(
            headline=Headline(column="e_w1", direction="min"),
            panels=(
                Panel(column="e_w1", label="energy W1", target=None),
                Panel(column="active_frac_w1", label="active-frac W1", target=None),
                Panel(column="radial_l2_log", label="radial L2 log", target=None),
                Panel(column="gen_max_to_real_max", label="gen_max / real", target=1.0),
            ),
        ),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)

    apply_campaigns_migration(lab_with_db.runs_db)
    conn = sqlite3.connect(lab_with_db.runs_db)
    _insert_run(
        conn, run_id="r1", started_at="2026-05-18T01:00:00Z",
        config_yaml="x", config_hash="h", model="qfm",
        eval_kind="sample", e_w1=25.0, active_frac_w1=0.5,
        radial_l2_log=1.234, gen_max_to_real_max=0.9,
    )
    conn.commit()
    conn.close()

    out = write_progress(lab_with_db)
    html = out.read_text()
    assert "best so far" in html
    # Each metric short label should appear in the header stat row
    assert "energy W1" in html
    assert "active-frac W1" in html
    assert "radial L2 log" in html
    assert "gen_max / real" in html
    # Values render
    assert "25.0000" in html  # e_w1
    assert "0.5000" in html   # active_frac_w1
    assert "1.2340" in html   # radial_l2_log
    assert "0.9000" in html   # gen_max_to_real_max


def test_sample_eval_filter_excludes_recon(lab_with_db, tmp_path):
    """A row with eval_kind='recon' and a tiny e_w1 must NOT become the headline.

    Recon W1 and sample W1 are not comparable; only sample evals are shown.
    The LabConfig must include e_w1 as a panel for the value to appear in header.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.yaml").touch()
    cfg = LabConfig(
        lab_id="qfm-diffusion", domain="quantum", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command="echo {config_path}", smoke_command=None,
            config_template=src / "c.yaml",
        ),
        metrics=Metrics(
            headline=Headline(column="e_w1", direction="min"),
            panels=(Panel(column="e_w1", label="energy W1", target=None),),
        ),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)

    apply_campaigns_migration(lab_with_db.runs_db)
    conn = sqlite3.connect(lab_with_db.runs_db)
    _insert_run(conn, run_id="r-recon", started_at="2026-05-18T01:00:00Z",
                config_yaml="x", config_hash="h", model="qfm",
                eval_kind="recon", e_w1=0.05, samples_png=None)
    _insert_run(conn, run_id="r-sample", started_at="2026-05-18T02:00:00Z",
                config_yaml="x", config_hash="h", model="qfm",
                eval_kind="sample", e_w1=27.0, samples_png=None)
    conn.commit()
    conn.close()

    out = write_progress(lab_with_db)
    html = out.read_text()
    # Headline best-W1 must show 27.0000 (the sample-eval row), not 0.0500 (recon)
    assert "27.0000" in html
    assert "0.0500" not in html


def test_architectures_section_groups_by_git_commit(lab_with_db):
    """Two runs sharing a git_commit should appear under one <details class="arch">."""
    apply_campaigns_migration(lab_with_db.runs_db)
    conn = sqlite3.connect(lab_with_db.runs_db)
    # Make sure the column exists (test fixture's CREATE TABLE doesn't include git_commit)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    if "git_commit" not in cols:
        conn.execute("ALTER TABLE runs ADD COLUMN git_commit TEXT")
    for run_id, sha in (("r1", "abc1234"), ("r2", "abc1234"), ("r3", "def5678")):
        _insert_run(
            conn, run_id=run_id, started_at=f"2026-05-18T0{run_id[-1]}:00:00Z",
            config_yaml="x", config_hash="h", model="qfm",
            eval_kind="sample", e_w1=20.0 + int(run_id[-1]), git_commit=sha,
        )
    conn.commit()
    conn.close()

    out = write_progress(lab_with_db)
    html = out.read_text()
    # Both architectures appear in the Architectures section
    assert "abc1234" in html
    assert "def5678" in html
    # Two <details class="arch"> blocks
    assert html.count('<details class="arch">') == 2
    assert "Architectures</h2>" in html


def test_conversation_panel_removed(lab_with_db):
    """The two-pane convo section was removed; the dashboard must not render it."""
    apply_campaigns_migration(lab_with_db.runs_db)
    out = write_progress(lab_with_db)
    html = out.read_text()
    assert "Your direction" not in html
    assert "Agent narrative" not in html
    assert 'class="convo"' not in html


def test_architecture_summary_has_thumbnail(lab_with_db, tmp_path):
    """Each architecture's summary row carries an inline thumbnail so the user
    decides which to expand based on the visual, not just the SHA."""
    apply_campaigns_migration(lab_with_db.runs_db)
    conn = sqlite3.connect(lab_with_db.runs_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    if "git_commit" not in cols:
        conn.execute("ALTER TABLE runs ADD COLUMN git_commit TEXT")
    # Real 1x1 PNG
    sample = tmp_path / "fake.png"
    sample.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
        b"\xc0\xf0\x1f\x00\x05\x00\x01\xff\xa3\xa7-\x99\x00\x00\x00\x00IEND"
        b"\xaeB`\x82"
    )
    _insert_run(
        conn, run_id="r1", started_at="2026-05-18T01:00:00Z",
        config_yaml="x", config_hash="h", model="qfm",
        eval_kind="sample", e_w1=20.0,
        samples_png=str(sample.relative_to(tmp_path.parent)),
        git_commit="abc1234",
    )
    conn.commit()
    conn.close()

    import os
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path.parent)
        out = write_progress(lab_with_db)
    finally:
        os.chdir(cwd)
    html = out.read_text()
    # Thumbnail must be inside the <summary>, not just in the expanded body.
    # We check that an img with class="arch-thumb" exists.
    assert 'class="arch-thumb"' in html
    # And that it appears before the matching </summary> tag of an arch detail.
    summary_open = html.find('<details class="arch"><summary>')
    summary_close = html.find('</summary>', summary_open)
    assert summary_open != -1 and summary_close != -1
    assert 'class="arch-thumb"' in html[summary_open:summary_close]


def test_image_click_opens_lightbox(lab_with_db, tmp_path):
    """Each sample tile wraps its <img> in <a href="#zoom-..."> and a matching
    <div class="lightbox" id="zoom-..."> exists at the end of the document so
    clicking the image enlarges it via CSS :target."""
    apply_campaigns_migration(lab_with_db.runs_db)
    conn = sqlite3.connect(lab_with_db.runs_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    if "git_commit" not in cols:
        conn.execute("ALTER TABLE runs ADD COLUMN git_commit TEXT")
    sample = tmp_path / "fake.png"
    sample.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
        b"\xc0\xf0\x1f\x00\x05\x00\x01\xff\xa3\xa7-\x99\x00\x00\x00\x00IEND"
        b"\xaeB`\x82"
    )
    # run_id intentionally contains chars that need sanitizing in the fragment
    _insert_run(
        conn, run_id="2026:05:18T01.00:00-abc-qfm",
        started_at="2026-05-18T01:00:00Z",
        config_yaml="x", config_hash="h", model="qfm",
        eval_kind="sample", e_w1=20.0,
        samples_png=str(sample.relative_to(tmp_path.parent)),
        git_commit="abc1234",
    )
    conn.commit()
    conn.close()

    import os
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path.parent)
        out = write_progress(lab_with_db)
    finally:
        os.chdir(cwd)
    html = out.read_text()

    # The thumbnail must be wrapped in an anchor pointing at a fragment id.
    # That same id must appear as a <div class="lightbox" id="...">.
    import re
    href_match = re.search(r'<a class="thumb-link" href="#(zoom-[^"]+)"', html)
    assert href_match, "thumb-link anchor missing"
    zoom_id = href_match.group(1)
    assert f'<div class="lightbox" id="{zoom_id}"' in html
    # Lightbox has a backdrop close anchor + close button
    assert 'class="lightbox-backdrop"' in html
    assert 'class="lightbox-close"' in html
    # Caption is included so users know which run they're zoomed into
    assert "lightbox-caption" in html
    # Fragment id contains no colons / dots (the run_id had both)
    assert ":" not in zoom_id and "." not in zoom_id


def test_run_tile_is_clickable_details(lab_with_db, tmp_path):
    """Each sample tile in the galleries is a <details> element (clickable)."""
    apply_campaigns_migration(lab_with_db.runs_db)
    conn = sqlite3.connect(lab_with_db.runs_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    if "git_commit" not in cols:
        conn.execute("ALTER TABLE runs ADD COLUMN git_commit TEXT")
    # Create a real PNG file so it embeds
    sample = tmp_path / "fake.png"
    # 1x1 transparent PNG bytes
    sample.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
        b"\xc0\xf0\x1f\x00\x05\x00\x01\xff\xa3\xa7-\x99\x00\x00\x00\x00IEND"
        b"\xaeB`\x82"
    )
    _insert_run(
        conn, run_id="r1", started_at="2026-05-18T01:00:00Z",
        config_yaml="x", config_hash="h", model="qfm",
        eval_kind="sample", e_w1=20.0,
        samples_png=str(sample.relative_to(tmp_path.parent)),
        git_commit="abc1234",
    )
    conn.commit()
    conn.close()

    # Render with cwd set so the relative samples_png resolves
    import os
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path.parent)
        out = write_progress(lab_with_db)
    finally:
        os.chdir(cwd)
    html = out.read_text()
    assert '<details class="run-tile">' in html
    # The detail panel contains the per-run kv block
    assert "config_hash" in html
    assert "researcher_mode" in html


def test_campaign_card_appears(lab_with_db):
    apply_campaigns_migration(lab_with_db.runs_db)
    conn = sqlite3.connect(lab_with_db.runs_db)
    conn.execute(
        """INSERT INTO campaigns
           (id, lab_id, question, hypothesis_path, hypothesis_hash, opened_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("c-test1", "qfm-diffusion", "does X help?",
         "popper-corpus/c-test1/hypothesis.md", "sha256:" + "0" * 64,
         "2026-05-18T00:00:00Z"),
    )
    _insert_run(conn, run_id="r1", started_at="2026-05-18T03:00:00Z",
                config_yaml="x", config_hash="h", model="qfm",
                eval_kind="sample", e_w1=25.0, campaign_id="c-test1")
    conn.commit()
    conn.close()

    out = write_progress(lab_with_db)
    html = out.read_text()
    assert "c-test1" in html
    assert "does X help?" in html
    assert "status-open" in html  # not closed yet
