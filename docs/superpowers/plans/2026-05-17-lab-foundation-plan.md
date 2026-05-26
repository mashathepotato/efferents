# Lab Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase A from `docs/superpowers/specs/2026-05-17-lab-foundation-design.md` — Researcher modes, campaigns, Popper-Probe gate, lab identity, agent-readable paper artifacts.

**Architecture:** Additive only. New SQLite columns + new `campaigns` table; new `agents/popper_gate.py` helper that single-shot-invokes Popper Probe's intake prompt and validates with its existing CLI; new `auto_qml/lab.py` identity stub; new `auto_qml/schemas/paper_frontmatter.py` pydantic schema + body structural validator; prompt branches in existing `agents/prompts/*.md`; existing Researcher/Executor/Analyst/Writer modules extended, not rewritten. The orchestrator stays a `while True:` loop with file-based state.

**Tech Stack:** Python 3.10+ (uv venv at `.venv`), `anthropic>=0.40`, `pyyaml`, SQLite via stdlib, `pydantic` (NEW dep, see Task 1), `pytest` for tests. Popper-probe repo at `~/Documents/popper-probe` (env `POPPER_PROBE_REPO` overrides).

**Worktree note:** The orchestrator runs 24/7 on `main`. Recommended: do this work in an isolated worktree via `superpowers:using-git-worktrees` so the live loop is undisturbed until merged.

---

## File Structure

**Create:**
- `tests/` — new directory; `tests/__init__.py`, `tests/conftest.py`, plus one test file per task.
- `auto_qml/lab.py` — lab identity constants. Imported by Writer, Analyst.
- `auto_qml/schemas/__init__.py` — package init.
- `auto_qml/schemas/paper_frontmatter.py` — pydantic models + body structural validator (single file: schema + a tiny markdown structure checker).
- `auto_qml/migrations/__init__.py` — package init.
- `auto_qml/migrations/2026-05-17_campaigns.sql` — DDL for `campaigns` table + `runs.campaign_id` + `runs.researcher_mode`.
- `auto_qml/migrations/runner.py` — small idempotent migration applier (PRAGMA table_info check before ALTER TABLE).
- `agents/popper_gate.py` — Popper Probe headless invocation: load SKILL.md as system prompt, single-shot call, write file, subprocess-validate.

**Modify:**
- `pyproject.toml` — add `pydantic>=2.0` to runtime deps.
- `agents/state.py` — campaign CRUD helpers, `recent_runs` SELECT extended to include new columns.
- `agents/orchestrator.py` — mode selector heuristic, `force_mode:` override reader, campaign 48h force-close in `step()`, novelty-gate hook before Writer trigger.
- `agents/researcher.py` — accept `mode` argument, route to prompt-section branch, call popper-gate when opening a campaign, tag proposals with `campaign_id` + `mode`, enforce ≤2 open campaigns cap.
- `agents/executor.py` — flow `campaign_id` and `researcher_mode` from proposal into `auto_qml.run` invocation via config overrides.
- `agents/analyst.py` — group recent runs by `campaign_id` when composing digest input.
- `agents/writer.py` — emit pydantic-validated YAML frontmatter; emit five required body sections; run structural self-check; respect novelty/gain gate from orchestrator.
- `agents/prompts/researcher.md` — add per-mode sections (`refine`, `moonshot`, `devils_advocate`, `escape_to_code`).
- `agents/prompts/writer.md` — required-sections discipline + completeness rule.
- `auto_qml/run.py` — extend `RUNS_SCHEMA` with `campaign_id TEXT NULL, researcher_mode TEXT NULL` (so fresh DBs match migrated DBs); write the values into the row from config.
- `agents/__main__.py` — apply migration at orchestrator startup (idempotent; no-op if already applied).

---

## Task 1: Test infrastructure + pydantic dep

**Files:**
- Create: `tests/__init__.py`, `tests/conftest.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pydantic to runtime dependencies**

Modify `pyproject.toml`, adding to the `dependencies` list:

```toml
    "pydantic>=2.0",
```

- [ ] **Step 2: Sync the venv**

Run: `uv sync --extra dev`
Expected: `pydantic` and `pytest` installed; no errors.

- [ ] **Step 3: Create test package init**

`tests/__init__.py` — empty file.

- [ ] **Step 4: Create conftest with shared fixtures**

`tests/conftest.py`:

```python
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

    def __init__(self, responses: list[str]):
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
```

- [ ] **Step 5: Verify pytest collects (no tests yet)**

Run: `uv run pytest tests/ -v`
Expected: `no tests ran in 0.0Xs` (exit 5 is OK when no tests collected).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/__init__.py tests/conftest.py
git commit -m "test: scaffold pytest fixtures + pydantic dep"
```

---

## Task 2: Campaigns migration + state helpers

**Files:**
- Create: `auto_qml/migrations/__init__.py`, `auto_qml/migrations/2026-05-17_campaigns.sql`, `auto_qml/migrations/runner.py`, `tests/test_migrations.py`, `tests/test_campaigns.py`
- Modify: `agents/state.py` (append helpers; do not touch existing ones)

- [ ] **Step 1: Create migrations package init**

`auto_qml/migrations/__init__.py` — empty file.

- [ ] **Step 2: Write the migration SQL**

`auto_qml/migrations/2026-05-17_campaigns.sql`:

```sql
-- Phase A: campaigns table + new columns on runs.
-- Idempotent at the table level; the runner checks PRAGMA table_info(runs)
-- before issuing ALTER TABLE.

CREATE TABLE IF NOT EXISTS campaigns (
    id              TEXT PRIMARY KEY,
    lab_id          TEXT NOT NULL,
    question        TEXT NOT NULL,
    hypothesis_path TEXT NOT NULL,
    hypothesis_hash TEXT NOT NULL,
    opened_at       TEXT NOT NULL,
    closed_at       TEXT,
    close_reason    TEXT
);

CREATE INDEX IF NOT EXISTS idx_campaigns_lab_open
    ON campaigns(lab_id) WHERE closed_at IS NULL;
```

- [ ] **Step 3: Write failing test for the runner**

`tests/test_migrations.py`:

```python
"""Migration runner must be idempotent and add the right columns."""
from __future__ import annotations

import sqlite3

import pytest

from auto_qml.migrations.runner import apply_campaigns_migration


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
```

- [ ] **Step 4: Run, verify it fails**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: ImportError (no `auto_qml.migrations.runner`).

- [ ] **Step 5: Implement the runner**

`auto_qml/migrations/runner.py`:

```python
"""Idempotent migration applier for Phase A campaign schema.

SQLite has no `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, so we
PRAGMA table_info first and only ALTER when missing.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATION_SQL = Path(__file__).parent / "2026-05-17_campaigns.sql"

_NEW_COLUMNS = (
    ("campaign_id", "TEXT"),
    ("researcher_mode", "TEXT"),
)


def apply_campaigns_migration(db_path: str | Path) -> None:
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(MIGRATION_SQL.read_text())
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        for name, sqltype in _NEW_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {sqltype}")
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 6: Run, verify all migration tests pass**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: 4 passed.

- [ ] **Step 7: Write failing test for campaign state helpers**

`tests/test_campaigns.py`:

```python
"""Campaign CRUD + cap + force-close helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.state import (
    campaign_close,
    campaign_insert,
    campaign_open_list,
    campaign_stale_open,
)
from auto_qml.migrations.runner import apply_campaigns_migration


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
```

- [ ] **Step 8: Run, verify it fails**

Run: `uv run pytest tests/test_campaigns.py -v`
Expected: ImportError on `campaign_insert` etc.

- [ ] **Step 9: Implement campaign helpers in state.py**

Append to `agents/state.py`:

```python
# ---------- Campaigns (Phase A) ----------

def campaign_insert(
    db_path: Path,
    *,
    id: str,
    lab_id: str,
    question: str,
    hypothesis_path: str,
    hypothesis_hash: str,
    opened_at: str | None = None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO campaigns
                 (id, lab_id, question, hypothesis_path, hypothesis_hash, opened_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (id, lab_id, question, hypothesis_path, hypothesis_hash, opened_at or now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def campaign_close(db_path: Path, id: str, *, reason: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE campaigns SET closed_at = ?, close_reason = ? WHERE id = ?",
            (now_iso(), reason, id),
        )
        conn.commit()
    finally:
        conn.close()


def campaign_open_list(db_path: Path, lab_id: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM campaigns WHERE lab_id = ? AND closed_at IS NULL",
            (lab_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def campaign_stale_open(
    db_path: Path, lab_id: str, *, hours: float = 48.0
) -> list[dict[str, Any]]:
    """Open campaigns where the most recent associated run (or, if no runs,
    `opened_at`) is older than `hours`."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT c.* FROM campaigns c
            LEFT JOIN runs r ON r.campaign_id = c.id
            WHERE c.lab_id = ? AND c.closed_at IS NULL
            GROUP BY c.id
            HAVING COALESCE(MAX(r.started_at), c.opened_at) < ?
            """,
            (lab_id, cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
```

Add `from datetime import timedelta` at the top of the imports if not already present (it is, in the existing file).

- [ ] **Step 10: Run, verify all campaign tests pass**

Run: `uv run pytest tests/test_campaigns.py -v`
Expected: 4 passed.

- [ ] **Step 11: Commit**

```bash
git add auto_qml/migrations/ agents/state.py tests/test_migrations.py tests/test_campaigns.py
git commit -m "feat(db): campaigns table + idempotent migration + state helpers"
```

---

## Task 3: Lab identity module

**Files:**
- Create: `auto_qml/lab.py`, `tests/test_lab.py`

- [ ] **Step 1: Write failing test**

`tests/test_lab.py`:

```python
"""Lab identity constants — single source of truth for who this lab is."""
from auto_qml import lab


def test_required_constants_present():
    assert isinstance(lab.LAB_ID, str) and lab.LAB_ID
    assert isinstance(lab.DOMAIN, str) and lab.DOMAIN
    assert isinstance(lab.CODE_REPO, str) and lab.CODE_REPO.startswith("http")


def test_subdomain_optional_but_str_if_present():
    assert lab.SUBDOMAIN is None or isinstance(lab.SUBDOMAIN, str)


def test_pi_handle_optional_but_str_if_present():
    assert lab.PI_HANDLE is None or isinstance(lab.PI_HANDLE, str)
```

- [ ] **Step 2: Run, verify it fails**

Run: `uv run pytest tests/test_lab.py -v`
Expected: ImportError on `auto_qml.lab`.

- [ ] **Step 3: Implement the module**

`auto_qml/lab.py`:

```python
"""Lab identity. The single place that names *this* lab; Phase B sibling
labs only differ from auto-qml in the constants below."""

LAB_ID: str = "qfm-diffusion"
DOMAIN: str = "quantum-ml"
SUBDOMAIN: str | None = "qfm-diffusion-hep"
PI_HANDLE: str | None = "@mashathepotato"
CODE_REPO: str = "https://github.com/mashathepotato/auto-qml"
```

- [ ] **Step 4: Run, verify passes**

Run: `uv run pytest tests/test_lab.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add auto_qml/lab.py tests/test_lab.py
git commit -m "feat(lab): identity constants module"
```

---

## Task 4: Paper frontmatter schema + body structural validator

**Files:**
- Create: `auto_qml/schemas/__init__.py`, `auto_qml/schemas/paper_frontmatter.py`, `tests/test_paper_frontmatter.py`

- [ ] **Step 1: Create package init**

`auto_qml/schemas/__init__.py` — empty file.

- [ ] **Step 2: Write failing tests**

`tests/test_paper_frontmatter.py`:

```python
"""Paper frontmatter schema (pydantic) + body structural validator."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from auto_qml.schemas.paper_frontmatter import (
    MetricProvenance,
    PaperFrontmatter,
    REQUIRED_SECTIONS_IN_ORDER,
    structural_check,
)


def _valid_frontmatter_kwargs():
    return dict(
        lab_id="qfm-diffusion",
        domain="quantum-ml",
        subdomain="qfm-diffusion-hep",
        pi_handle="@mashathepotato",
        campaign_id="c-001",
        hypothesis_hash="sha256:" + "0" * 64,
        hypothesis_path="popper-corpus/foo/hypothesis.md",
        metric_provenance=[
            MetricProvenance(
                name="e_w1",
                value=0.012,
                delta_vs_baseline=-0.004,
                runs=["r1", "r2"],
                seeds=[0, 1, 2],
            )
        ],
        novelty_claim="first use of laplacian-pyramid UNet on QFM diffusion",
        published_at="2026-05-17",
        status="preprint",
    )


def test_valid_frontmatter_passes():
    PaperFrontmatter(**_valid_frontmatter_kwargs())


def test_missing_required_field_fails():
    kwargs = _valid_frontmatter_kwargs()
    del kwargs["lab_id"]
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)


def test_code_repo_and_sha_must_both_be_set_or_both_absent():
    kwargs = _valid_frontmatter_kwargs()
    kwargs["code_repo"] = "https://github.com/x/y"
    # code_sha absent → should fail
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)
    kwargs["code_sha"] = "abc1234"
    PaperFrontmatter(**kwargs)  # both set → OK
    kwargs["code_repo"] = None
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)


def test_novelty_claim_nonempty():
    kwargs = _valid_frontmatter_kwargs()
    kwargs["novelty_claim"] = "   "
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)


def test_status_constrained():
    kwargs = _valid_frontmatter_kwargs()
    kwargs["status"] = "published"  # not a Phase-A submission state
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)


def test_structural_check_accepts_all_five_sections_in_order():
    body = "\n".join(f"## {s}\nSome content.\n" for s in REQUIRED_SECTIONS_IN_ORDER)
    ok, errors = structural_check(body)
    assert ok and errors == []


def test_structural_check_rejects_missing_section():
    sections = REQUIRED_SECTIONS_IN_ORDER[:-1]  # drop "Next questions"
    body = "\n".join(f"## {s}\nSome content.\n" for s in sections)
    ok, errors = structural_check(body)
    assert not ok
    assert any("Next questions" in e for e in errors)


def test_structural_check_rejects_out_of_order():
    reordered = list(REQUIRED_SECTIONS_IN_ORDER)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    body = "\n".join(f"## {s}\nSome content.\n" for s in reordered)
    ok, errors = structural_check(body)
    assert not ok
    assert any("order" in e.lower() for e in errors)
```

- [ ] **Step 3: Run, verify it fails**

Run: `uv run pytest tests/test_paper_frontmatter.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement schema + validator**

`auto_qml/schemas/paper_frontmatter.py`:

```python
"""Schema for the platform-shaped Writer output.

Two halves: a pydantic model for the YAML frontmatter, and a small
structural check that the body contains the five required sections,
in order, with non-empty content.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


REQUIRED_SECTIONS_IN_ORDER: tuple[str, ...] = (
    "Motivation",
    "Methods",
    "Results",
    "Conclusion",
    "Next questions",
)


class MetricProvenance(BaseModel):
    name: str = Field(..., min_length=1)
    value: float
    delta_vs_baseline: float | None = None
    runs: list[str] = Field(..., min_length=1)
    seeds: list[int] = Field(..., min_length=1)


class PaperFrontmatter(BaseModel):
    lab_id: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)
    subdomain: str | None = None
    pi_handle: str | None = None
    campaign_id: str = Field(..., min_length=1)
    hypothesis_hash: str = Field(..., pattern=r"^sha256:[0-9a-f]{64}$")
    hypothesis_path: str = Field(..., min_length=1)
    code_repo: str | None = None
    code_sha: str | None = None
    metric_provenance: list[MetricProvenance] = Field(..., min_length=1)
    novelty_claim: str = Field(..., min_length=1)
    published_at: str = Field(..., min_length=1)
    status: Literal["preprint", "draft"]

    @model_validator(mode="after")
    def _code_pointers_paired(self) -> "PaperFrontmatter":
        if (self.code_repo is None) != (self.code_sha is None):
            raise ValueError(
                "code_repo and code_sha must both be set or both absent"
            )
        return self

    @model_validator(mode="after")
    def _novelty_claim_nontrivial(self) -> "PaperFrontmatter":
        if not self.novelty_claim.strip():
            raise ValueError("novelty_claim must be non-whitespace")
        return self


_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def structural_check(body: str) -> tuple[bool, list[str]]:
    """Return (ok, errors). Errors enumerate each violation found."""
    headers = _SECTION_RE.findall(body)
    errors: list[str] = []

    missing = [s for s in REQUIRED_SECTIONS_IN_ORDER if s not in headers]
    for s in missing:
        errors.append(f"missing required section: {s}")

    # Filter headers to just the required ones, preserving order, and check order.
    present = [h for h in headers if h in REQUIRED_SECTIONS_IN_ORDER]
    expected_order = [s for s in REQUIRED_SECTIONS_IN_ORDER if s in present]
    if present != expected_order:
        errors.append(
            f"sections out of order; got {present}, expected order {expected_order}"
        )

    # Non-empty body per required section
    sections = _split_sections(body)
    for s in REQUIRED_SECTIONS_IN_ORDER:
        if s in sections and not sections[s].strip():
            errors.append(f"section '{s}' is empty")

    return (len(errors) == 0, errors)


def _split_sections(body: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in body.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            if current is not None:
                parts[current] = "\n".join(buf).strip()
            current = m.group(1)
            buf = []
        else:
            if current is not None:
                buf.append(line)
    if current is not None:
        parts[current] = "\n".join(buf).strip()
    return parts
```

- [ ] **Step 5: Run, verify passes**

Run: `uv run pytest tests/test_paper_frontmatter.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add auto_qml/schemas/ tests/test_paper_frontmatter.py
git commit -m "feat(schemas): paper frontmatter pydantic model + body validator"
```

---

## Task 5: Popper Probe gate

**Files:**
- Create: `agents/popper_gate.py`, `tests/test_popper_gate.py`, `tests/fixtures/__init__.py`, `tests/fixtures/valid_hypothesis.md`, `tests/fixtures/invalid_hypothesis.md`

- [ ] **Step 1: Create fixture: valid hypothesis.md**

`tests/fixtures/__init__.py` — empty.

`tests/fixtures/valid_hypothesis.md`:

```markdown
---
slug: aug-depth-three
created: 2026-05-17
status: active
falsifiability_gate: passed
literature_pass: none
---

# Increasing aug_depth from 1 to 3 reduces W1 by ≥10% on QG1_64x64_1k within 500 epochs

## Original framing

> What if we just deepen the augmentation?

## Operational restatement

With config `default.yaml` and `aug_depth=3` (vs baseline `aug_depth=1`), trained for 500 epochs on QG1_64x64_1k, the energy-distance W1 metric on the val split will be at least 10% lower than the baseline, averaged across 3 seeds.

## Falsifier(s)

- If mean W1 across seeds is within 5% of baseline, claim fails.
- If W1 is worse than baseline at any seed, claim fails.

## Test design

Run baseline + treatment for 3 seeds each at 500 epochs. Use the existing `run.py` CLI. Compare mean W1.

## Auxiliary assumptions

- The W1 implementation in metrics.py is correct.
- 500 epochs is past the convergence elbow.

## Distinctiveness

Competing account (parameter-only fine-tune) predicts no effect; this one predicts ≥10% gain.

## References

## Intake log

- 2026-05-17: drafted from Researcher proposal; passed all probes.
```

`tests/fixtures/invalid_hypothesis.md`:

```markdown
---
created: 2026-05-17
---

# Make W1 better

## Original framing

> idk just make it better
```

- [ ] **Step 2: Write failing tests for the gate**

`tests/test_popper_gate.py`:

```python
"""popper_gate.run runs single-shot self-play and validates output."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from agents.popper_gate import GateResult, run_gate


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def popper_repo(monkeypatch, tmp_path):
    """Build a minimal popper-probe-shaped directory with the canonical
    SKILL.md and validate_hypothesis.py so the gate can find them without
    depending on the user's working copy."""
    repo = tmp_path / "popper-probe"
    (repo / "skills" / "intake").mkdir(parents=True)
    (repo / "scripts").mkdir()
    # Use the real SKILL.md from the user's working copy so we test against
    # the actual content; fall back to a stub if absent.
    real_skill = Path.home() / "Documents/popper-probe/skills/intake/SKILL.md"
    real_validator = Path.home() / "Documents/popper-probe/scripts/validate_hypothesis.py"
    skill_dst = repo / "skills/intake/SKILL.md"
    if real_skill.exists():
        skill_dst.write_text(real_skill.read_text())
    else:
        skill_dst.write_text("# Stub SKILL.md\n")
    if real_validator.exists():
        (repo / "scripts/validate_hypothesis.py").write_text(real_validator.read_text())
    else:
        pytest.skip("Real popper-probe validate_hypothesis.py not available")
    monkeypatch.setenv("POPPER_PROBE_REPO", str(repo))
    return repo


def test_accept_path_writes_file_and_returns_hash(
    popper_repo, tmp_path, fake_anthropic_factory
):
    valid_text = (FIXTURES / "valid_hypothesis.md").read_text()
    client = fake_anthropic_factory([valid_text])
    out_root = tmp_path / "popper-corpus"

    result = run_gate(
        draft_claim="aug_depth=3 should reduce W1 by 10%",
        slug="aug-depth-three",
        corpus_root=out_root,
        client=client,
    )

    assert isinstance(result, GateResult)
    assert result.ok
    assert result.path == out_root / "aug-depth-three/hypothesis.md"
    assert result.path.exists()
    assert result.path.read_text() == valid_text
    assert result.hash.startswith("sha256:")
    assert len(result.hash) == len("sha256:") + 64


def test_reject_then_drop_after_one_retry(
    popper_repo, tmp_path, fake_anthropic_factory
):
    invalid_text = (FIXTURES / "invalid_hypothesis.md").read_text()
    client = fake_anthropic_factory([invalid_text, invalid_text])
    out_root = tmp_path / "popper-corpus"

    result = run_gate(
        draft_claim="something fuzzy",
        slug="fuzzy",
        corpus_root=out_root,
        client=client,
    )

    assert not result.ok
    assert result.reason
    assert "validate" in result.reason.lower() or "schema" in result.reason.lower()
    # The model was retried once → 2 calls total
    assert len(client.calls) == 2


def test_retry_succeeds(popper_repo, tmp_path, fake_anthropic_factory):
    invalid_text = (FIXTURES / "invalid_hypothesis.md").read_text()
    valid_text = (FIXTURES / "valid_hypothesis.md").read_text()
    client = fake_anthropic_factory([invalid_text, valid_text])
    out_root = tmp_path / "popper-corpus"

    result = run_gate(
        draft_claim="retry case",
        slug="retry-case",
        corpus_root=out_root,
        client=client,
    )

    assert result.ok
    assert len(client.calls) == 2
    # On retry, the user message must include the validator's errors so the
    # model can correct course
    second_user_msgs = client.calls[1].get("messages", [])
    assert any("ERROR" in str(m) or "validator" in str(m).lower() for m in second_user_msgs)
```

- [ ] **Step 3: Run, verify it fails**

Run: `uv run pytest tests/test_popper_gate.py -v`
Expected: ImportError on `agents.popper_gate`.

- [ ] **Step 4: Implement the gate**

`agents/popper_gate.py`:

```python
"""Headless Popper Probe intake for the orchestrator.

Single-shot self-play: load SKILL.md as system prompt, ask the model to
play both roles (claimant + Popperian probe) and emit ONLY the
hypothesis.md contents. Subprocess-validate with popper-probe's existing
CLI. One retry on validator fail.

Popper-probe repo location: env POPPER_PROBE_REPO, default ~/Documents/popper-probe.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _popper_repo() -> Path:
    return Path(os.environ.get("POPPER_PROBE_REPO", str(Path.home() / "Documents/popper-probe")))


def _skill_md() -> str:
    return (_popper_repo() / "skills/intake/SKILL.md").read_text()


def _validator() -> Path:
    return _popper_repo() / "scripts/validate_hypothesis.py"


_HEADLESS_INSTRUCTION = """
HEADLESS MODE — IMPORTANT

You are running without an interactive user. Play BOTH roles yourself:
the claimant (using the draft claim below as their starting position)
AND the Popperian probe. Run Probes 1, 2, and 3 internally. Probe 0
(SoTA orientation) is skipped. Probe 4 (distinctiveness) is recorded as
flagged or substantive.

If Probe 1 or Probe 2 cannot be satisfied even after a real sharpening
attempt, emit a hypothesis.md with `falsifiability_gate: failed`,
`status: unfalsifiable`, and a `## Diagnostic` section. Otherwise emit
`falsifiability_gate: passed`, `status: active`, and the full body
sections per the schema.

Output ONLY the hypothesis.md file contents (YAML frontmatter +
markdown body). No commentary, no code fences, no preamble. Your first
character must be a literal "---" opening the frontmatter.
""".strip()


@dataclass
class GateResult:
    ok: bool
    path: Path | None
    hash: str | None
    reason: str | None  # populated on failure


def _hash_file(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def _extract_text(response: Any) -> str:
    return "".join(block.text for block in response.content if getattr(block, "type", "text") == "text")


def _validate(path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(_validator()), str(path)],
        capture_output=True, text=True,
    )
    return (proc.returncode == 0, (proc.stderr or proc.stdout).strip())


def run_gate(
    *,
    draft_claim: str,
    slug: str,
    corpus_root: Path,
    client: Any,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
) -> GateResult:
    """Run single-shot self-play intake. Writes hypothesis.md on success.

    Returns GateResult with ok=True/path/hash on accept, or ok=False/reason
    on drop after one retry.
    """
    out_dir = corpus_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "hypothesis.md"

    system = _skill_md() + "\n\n" + _HEADLESS_INSTRUCTION

    user_first = (
        f"Draft claim to process:\n\n{draft_claim}\n\n"
        f"Emit the hypothesis.md for slug `{slug}` now."
    )
    last_errors = ""

    for attempt in (1, 2):
        if attempt == 1:
            user_msg = user_first
        else:
            user_msg = (
                f"{user_first}\n\n"
                f"Your previous output failed validate_hypothesis.py with:\n\n"
                f"{last_errors}\n\n"
                f"Emit a corrected hypothesis.md. Same output rules apply."
            )
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        body = _extract_text(response).strip()
        out_path.write_text(body)
        ok, errors = _validate(out_path)
        if ok:
            return GateResult(ok=True, path=out_path, hash=_hash_file(out_path), reason=None)
        last_errors = errors

    return GateResult(ok=False, path=None, hash=None, reason=f"validator: {last_errors}")
```

- [ ] **Step 5: Run, verify all gate tests pass**

Run: `uv run pytest tests/test_popper_gate.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add agents/popper_gate.py tests/test_popper_gate.py tests/fixtures/
git commit -m "feat(popper): headless single-shot intake gate with subprocess validation"
```

---

## Task 6: Researcher mode plumbing (prompt branching + proposal tagging)

**Files:**
- Modify: `agents/researcher.py`, `agents/prompts/researcher.md`
- Create: `tests/test_researcher_modes.py`

- [ ] **Step 1: Add per-mode sections to the prompt**

Modify `agents/prompts/researcher.md` — at the end of the existing prompt, append:

```markdown

## Modes

You may be invoked in one of four modes. The mode is passed to you in
the user message as `<<MODE: name>>`. Tailor your proposals accordingly.

### refine

Propose 1–3 configs close to recent good runs. Small, targeted
parameter moves. Default mode; use when the metric trend is healthy.

### moonshot

The metric has plateaued. Propose configs that violate a recent
assumption — different scheduler, very different `aug_depth`, novel
encoding, etc. Bias toward 1 bold move over 3 incremental ones.

### devils_advocate

The current best result may be fragile. Propose a config designed to
*break* the trend or expose a confound. If the Student/Supervisor
fidelity gates look thin, say so in `hypothesis`.

### escape_to_code

Parametric space is exhausted. Propose an architectural change rather
than a config tweak. Write the proposed change description to
`proposed_changes.md` AND emit a `mode: "escape_to_code"` proposal that
the Coder will pick up.
```

- [ ] **Step 2: Write failing test for mode-tagged proposal**

`tests/test_researcher_modes.py`:

```python
"""Researcher accepts a mode argument, injects it into the prompt, and
tags emitted proposals with it."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import researcher
from agents.state import LabPaths, lab_paths, init_lab


@pytest.fixture
def paths(tmp_lab):
    p = lab_paths(tmp_lab)
    init_lab(p)
    return p


def _fake_proposals_json(mode: str) -> str:
    return json.dumps(
        {
            "proposals": [
                {
                    "name": "p1",
                    "hypothesis": "test",
                    "expected": "x",
                    "config_overrides": {"run.seed": 7},
                }
            ]
        }
    )


def test_mode_injected_into_user_message(paths, fake_anthropic_factory, tmp_path):
    client = fake_anthropic_factory([_fake_proposals_json("moonshot")])

    class FakeBudget:
        def should_pause(self): return False
        def record(self, *a, **k): pass
        def daily_total(self): return 0.0

    researcher.propose(
        paths=paths,
        context_dir=tmp_path,
        budget=FakeBudget(),
        client=client,
        mode="moonshot",
    )

    user_msg = client.calls[0]["messages"][0]["content"]
    assert "<<MODE: moonshot>>" in str(user_msg)


def test_proposals_tagged_with_mode(paths, fake_anthropic_factory, tmp_path):
    client = fake_anthropic_factory([_fake_proposals_json("devils_advocate")])

    class FakeBudget:
        def should_pause(self): return False
        def record(self, *a, **k): pass
        def daily_total(self): return 0.0

    result = researcher.propose(
        paths=paths,
        context_dir=tmp_path,
        budget=FakeBudget(),
        client=client,
        mode="devils_advocate",
    )
    proposals = result.get("proposals", [])
    assert proposals
    assert all(p.get("mode") == "devils_advocate" for p in proposals)


def test_mode_defaults_to_refine_when_omitted(paths, fake_anthropic_factory, tmp_path):
    client = fake_anthropic_factory([_fake_proposals_json("refine")])

    class FakeBudget:
        def should_pause(self): return False
        def record(self, *a, **k): pass
        def daily_total(self): return 0.0

    researcher.propose(
        paths=paths,
        context_dir=tmp_path,
        budget=FakeBudget(),
        client=client,
    )
    user_msg = client.calls[0]["messages"][0]["content"]
    assert "<<MODE: refine>>" in str(user_msg)
```

- [ ] **Step 3: Run, verify it fails**

Run: `uv run pytest tests/test_researcher_modes.py -v`
Expected: `TypeError: propose() got an unexpected keyword argument 'mode'` or similar.

- [ ] **Step 4: Modify `agents/researcher.py`'s `propose()` signature**

Open `agents/researcher.py`. Locate the `propose(...)` function. Add a `mode: str = "refine"` keyword argument. Where the user message is composed (the f-string that builds the user content for the SDK call), prepend a literal `<<MODE: {mode}>>\n\n` line so the model sees it.

Where proposals are extracted from the model's JSON output and returned to the caller (look for the dict that contains `"proposals": [...]`), tag each proposal dict with `p["mode"] = mode` before returning.

- [ ] **Step 5: Run, verify tests pass**

Run: `uv run pytest tests/test_researcher_modes.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add agents/researcher.py agents/prompts/researcher.md tests/test_researcher_modes.py
git commit -m "feat(researcher): explicit mode plumbing (refine/moonshot/devils_advocate/escape_to_code)"
```

---

## Task 7: Mode selector + research_log override

**Files:**
- Modify: `agents/orchestrator.py`, `agents/state.py`
- Create: `tests/test_mode_selector.py`

- [ ] **Step 1: Write failing test**

`tests/test_mode_selector.py`:

```python
"""Mode selector heuristic + force_mode override from research_log.md."""
from __future__ import annotations

from pathlib import Path

import pytest

from agents.orchestrator import select_mode, read_force_mode


def _state(flat_digests=0):
    return {"digests_without_improvement": flat_digests}


def test_refine_when_no_flat_digests():
    assert select_mode(_state(0), override=None) == "refine"


def test_moonshot_at_two_flat_digests():
    assert select_mode(_state(2), override=None) == "moonshot"


def test_devils_advocate_at_three():
    assert select_mode(_state(3), override=None) == "devils_advocate"


def test_escape_to_code_at_four():
    assert select_mode(_state(4), override=None) == "escape_to_code"


def test_override_wins(tmp_path):
    assert select_mode(_state(0), override="moonshot") == "moonshot"


def test_unknown_override_falls_back(tmp_path):
    assert select_mode(_state(0), override="banana") == "refine"


def test_read_force_mode_returns_value(tmp_path):
    log = tmp_path / "research_log.md"
    log.write_text("Some narrative.\n\nforce_mode: devils_advocate\n\nMore narrative.\n")
    assert read_force_mode(tmp_path) == "devils_advocate"


def test_read_force_mode_returns_none_when_absent(tmp_path):
    log = tmp_path / "research_log.md"
    log.write_text("No directive here.\n")
    assert read_force_mode(tmp_path) is None


def test_read_force_mode_uses_last_occurrence(tmp_path):
    log = tmp_path / "research_log.md"
    log.write_text(
        "force_mode: moonshot\n\nsome notes\n\nforce_mode: refine\n"
    )
    assert read_force_mode(tmp_path) == "refine"
```

- [ ] **Step 2: Run, verify it fails**

Run: `uv run pytest tests/test_mode_selector.py -v`
Expected: ImportError on `select_mode` / `read_force_mode`.

- [ ] **Step 3: Implement in `agents/orchestrator.py`**

Add near the top of `agents/orchestrator.py` (after imports, before `Orchestrator` class):

```python
import re as _re

_VALID_MODES = {"refine", "moonshot", "devils_advocate", "escape_to_code"}
_FORCE_MODE_RE = _re.compile(r"^force_mode:\s*(\S+)\s*$", _re.MULTILINE)


def read_force_mode(context_dir: Path | str) -> str | None:
    """Return the LAST `force_mode: <name>` directive in research_log.md
    or None if absent / unreadable / name unknown."""
    log = Path(context_dir) / "research_log.md"
    if not log.exists():
        return None
    matches = _FORCE_MODE_RE.findall(log.read_text())
    if not matches:
        return None
    candidate = matches[-1].strip()
    return candidate if candidate in _VALID_MODES else None


def select_mode(state: dict, *, override: str | None) -> str:
    if override in _VALID_MODES:
        return override
    flat = int(state.get("digests_without_improvement", 0))
    if flat >= 4:
        return "escape_to_code"
    if flat >= 3:
        return "devils_advocate"
    if flat >= 2:
        return "moonshot"
    return "refine"
```

- [ ] **Step 4: Run, verify all selector tests pass**

Run: `uv run pytest tests/test_mode_selector.py -v`
Expected: 9 passed.

- [ ] **Step 5: Wire into `_refill_queue`**

Inside `Orchestrator._refill_queue`, BEFORE the `researcher.propose(...)` call, compute the mode:

```python
state = load_state(self.paths.state)
override = read_force_mode(self.context_dir)
mode = select_mode(state, override=override)
notebook_append(
    self.paths.notebook,
    f"## {now_iso()} — Researcher mode: {mode} "
    f"(flat_digests={state.get('digests_without_improvement', 0)}, override={override})\n"
)
```

Pass `mode=mode` to `researcher.propose(...)`. The state value `digests_without_improvement` is updated in Task 9 — for now it defaults to 0, which keeps behavior identical (everything is `refine`).

- [ ] **Step 6: Commit**

```bash
git add agents/orchestrator.py tests/test_mode_selector.py
git commit -m "feat(orchestrator): mode selector + research_log force_mode override"
```

---

## Task 8: Researcher opens campaigns via popper-gate (≤2 cap)

**Files:**
- Modify: `agents/researcher.py`, `agents/prompts/researcher.md`
- Create: `tests/test_researcher_campaign.py`

- [ ] **Step 1: Tell the prompt about the two-stage emission**

Append to `agents/prompts/researcher.md`:

```markdown

## Campaign emission

A campaign is a hypothesis under test, with proposals running against
it until it is resolved. You may have AT MOST 2 open campaigns at any
time (the orchestrator tells you which are open in the user message).

When you produce proposals, decide for EACH proposal:

- If the proposal belongs to an existing open campaign, set
  `campaign_id` to that campaign's id (the orchestrator names them in
  the user message).
- If the proposal opens a NEW campaign, also emit a sibling object
  `new_campaign: {question: "...", draft_hypothesis: "..."}` next to
  the `proposals` array in your JSON output. The orchestrator will run
  this draft through the falsifiability gate; if it passes, it opens
  a campaign and assigns its id to your proposals.
- If two open campaigns already exist and you would open a third, do
  not propose a new campaign — either route the proposal to an
  existing campaign or pivot to refining.

`draft_hypothesis` should be a single paragraph that names the
operational claim and a candidate falsifier. It is NOT the full
popper-format file; the gate produces that from your draft.

JSON shape:

```json
{
  "proposals": [
    {"name": "...", "hypothesis": "...", "expected": "...",
     "config_overrides": {...}, "campaign_id": "<existing-or-new>"}
  ],
  "new_campaign": {
    "question": "...",
    "draft_hypothesis": "..."
  }
}
```

If you do not open a new campaign, omit `new_campaign`.
```

- [ ] **Step 2: Write failing test**

`tests/test_researcher_campaign.py`:

```python
"""Researcher campaign open path: popper_gate runs, campaigns row inserted,
proposals tagged. ≤2 open campaigns cap enforced."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents import researcher
from agents.state import (
    campaign_insert,
    campaign_open_list,
    init_lab,
    lab_paths,
)
from auto_qml.migrations.runner import apply_campaigns_migration


@pytest.fixture
def paths(tmp_lab):
    p = lab_paths(tmp_lab)
    init_lab(p)
    # The state helpers expect runs.sqlite to exist with the new schema.
    # Initialize a minimal one.
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


def test_new_campaign_calls_gate_and_inserts_row(
    paths, fake_anthropic_factory, tmp_path, monkeypatch
):
    researcher_response = json.dumps({
        "proposals": [
            {"name": "p1", "hypothesis": "h", "expected": "e",
             "config_overrides": {"run.seed": 1}}
        ],
        "new_campaign": {
            "question": "does X help?",
            "draft_hypothesis": "X reduces W1 by 10% under default config."
        }
    })

    # Stub popper_gate to accept.
    from agents import popper_gate
    fake_result = popper_gate.GateResult(
        ok=True,
        path=paths.root / "popper-corpus/test/hypothesis.md",
        hash="sha256:" + "a" * 64,
        reason=None,
    )
    monkeypatch.setattr(popper_gate, "run_gate", lambda **kw: fake_result)

    client = fake_anthropic_factory([researcher_response])

    class FakeBudget:
        def should_pause(self): return False
        def record(self, *a, **k): pass
        def daily_total(self): return 0.0

    result = researcher.propose(
        paths=paths,
        context_dir=tmp_path,
        budget=FakeBudget(),
        client=client,
        mode="refine",
    )

    opens = campaign_open_list(paths.runs_db, "qfm-diffusion")
    assert len(opens) == 1
    assert opens[0]["hypothesis_hash"] == "sha256:" + "a" * 64
    # The proposal carries the new campaign's id
    proposals = result["proposals"]
    assert proposals[0]["campaign_id"] == opens[0]["id"]


def test_cap_blocks_third_open_campaign(
    paths, fake_anthropic_factory, tmp_path, monkeypatch
):
    # Pre-insert two open campaigns
    for i in (1, 2):
        campaign_insert(
            paths.runs_db,
            id=f"c{i}",
            lab_id="qfm-diffusion",
            question=f"q{i}",
            hypothesis_path=f"popper-corpus/c{i}/hypothesis.md",
            hypothesis_hash="sha256:" + str(i) * 64,
        )

    researcher_response = json.dumps({
        "proposals": [
            {"name": "p1", "hypothesis": "h", "expected": "e",
             "config_overrides": {"run.seed": 1}}
        ],
        "new_campaign": {
            "question": "third one?",
            "draft_hypothesis": "Z reduces W1."
        }
    })

    # If popper_gate is called when capped, the test fails — stub it to raise.
    from agents import popper_gate
    def _no_gate(**kw):
        raise AssertionError("gate must not be called when at cap")
    monkeypatch.setattr(popper_gate, "run_gate", _no_gate)

    client = fake_anthropic_factory([researcher_response])

    class FakeBudget:
        def should_pause(self): return False
        def record(self, *a, **k): pass
        def daily_total(self): return 0.0

    researcher.propose(
        paths=paths,
        context_dir=tmp_path,
        budget=FakeBudget(),
        client=client,
        mode="refine",
    )

    # Still only 2 open campaigns
    assert len(campaign_open_list(paths.runs_db, "qfm-diffusion")) == 2


def test_gate_reject_drops_new_campaign_but_keeps_proposals(
    paths, fake_anthropic_factory, tmp_path, monkeypatch
):
    researcher_response = json.dumps({
        "proposals": [
            {"name": "p1", "hypothesis": "h", "expected": "e",
             "config_overrides": {"run.seed": 1}}
        ],
        "new_campaign": {
            "question": "fuzzy?",
            "draft_hypothesis": "make things better"
        }
    })

    from agents import popper_gate
    fake_reject = popper_gate.GateResult(
        ok=False, path=None, hash=None, reason="validator: missing falsifier"
    )
    monkeypatch.setattr(popper_gate, "run_gate", lambda **kw: fake_reject)

    client = fake_anthropic_factory([researcher_response])

    class FakeBudget:
        def should_pause(self): return False
        def record(self, *a, **k): pass
        def daily_total(self): return 0.0

    result = researcher.propose(
        paths=paths,
        context_dir=tmp_path,
        budget=FakeBudget(),
        client=client,
        mode="refine",
    )

    assert campaign_open_list(paths.runs_db, "qfm-diffusion") == []
    # Proposals have no campaign_id (orphaned proposals are NOT enqueued —
    # see implementation: they're dropped, with a notebook note)
    assert result.get("proposals") == [] or all(
        p.get("campaign_id") is None for p in result["proposals"]
    )
```

- [ ] **Step 3: Run, verify failures**

Run: `uv run pytest tests/test_researcher_campaign.py -v`
Expected: failures (new behavior not implemented).

- [ ] **Step 4: Implement the campaign-open path in `agents/researcher.py`**

In `agents/researcher.py`, after the JSON parse (`parse_json_loose`) of the model's reply but before returning, add:

```python
# Phase A: handle new_campaign + ≤2 cap, gate via popper.
from auto_qml import lab as _lab
from agents import popper_gate as _popper_gate
from agents.state import (
    campaign_insert as _campaign_insert,
    campaign_open_list as _campaign_open_list,
)

new_campaign = parsed.get("new_campaign")
opens = _campaign_open_list(paths.runs_db, _lab.LAB_ID)
new_campaign_id: str | None = None
if new_campaign and len(opens) < 2:
    import uuid as _uuid
    slug = _slugify(new_campaign.get("question", "campaign"))[:48] + "-" + _uuid.uuid4().hex[:6]
    gate_result = _popper_gate.run_gate(
        draft_claim=new_campaign.get("draft_hypothesis", ""),
        slug=slug,
        corpus_root=paths.root.parent / "popper-corpus",
        client=client,
    )
    if gate_result.ok:
        campaign_id = "c-" + _uuid.uuid4().hex[:10]
        _campaign_insert(
            paths.runs_db,
            id=campaign_id,
            lab_id=_lab.LAB_ID,
            question=new_campaign.get("question", ""),
            hypothesis_path=str(gate_result.path.relative_to(paths.root.parent)),
            hypothesis_hash=gate_result.hash,
        )
        new_campaign_id = campaign_id
        notebook_append(
            paths.notebook,
            f"## {now_iso()} — opened campaign {campaign_id} "
            f"({new_campaign.get('question')!r}) hash={gate_result.hash[:14]}…\n",
        )
    else:
        notebook_append(
            paths.notebook,
            f"## {now_iso()} — popper-gate REJECTED draft hypothesis: "
            f"{gate_result.reason}\n",
        )

# Route proposals: if a proposal has no campaign_id, assign the new one
# (if any). If neither, drop the proposal with a notebook note.
final_proposals: list[dict] = []
for p in parsed.get("proposals", []):
    if p.get("campaign_id") is None:
        if new_campaign_id is not None:
            p["campaign_id"] = new_campaign_id
        else:
            notebook_append(
                paths.notebook,
                f"## {now_iso()} — dropped untagged proposal {p.get('name')!r}\n",
            )
            continue
    p["mode"] = mode
    final_proposals.append(p)
parsed["proposals"] = final_proposals
```

Also add a helper at module level:

```python
def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")
```

- [ ] **Step 5: Run, verify campaign tests pass**

Run: `uv run pytest tests/test_researcher_campaign.py -v`
Expected: 3 passed.

- [ ] **Step 6: Re-run all tests to confirm no regressions**

Run: `uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add agents/researcher.py agents/prompts/researcher.md tests/test_researcher_campaign.py
git commit -m "feat(researcher): open campaigns via popper-gate, enforce 2-open cap"
```

---

## Task 9: Campaign 48h force-close + digests_without_improvement counter

**Files:**
- Modify: `agents/orchestrator.py`, `agents/analyst.py`
- Create: `tests/test_force_close.py`, `tests/test_flat_digest_counter.py`

- [ ] **Step 1: Write failing test for force-close**

`tests/test_force_close.py`:

```python
"""Orchestrator closes campaigns with no new runs in 48h."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agents.orchestrator import close_stale_campaigns
from agents.state import (
    campaign_insert,
    campaign_open_list,
    init_lab,
    lab_paths,
)
from auto_qml.migrations.runner import apply_campaigns_migration


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
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/test_force_close.py -v`
Expected: ImportError on `close_stale_campaigns`.

- [ ] **Step 3: Implement `close_stale_campaigns` in orchestrator**

Add to `agents/orchestrator.py` (top-level function, near `select_mode`):

```python
from agents.state import campaign_stale_open, campaign_close


def close_stale_campaigns(db_path: Path, *, lab_id: str, hours: float = 48.0) -> list[str]:
    stale = campaign_stale_open(db_path, lab_id, hours=hours)
    ids = [c["id"] for c in stale]
    for cid in ids:
        campaign_close(db_path, cid, reason="stale")
    return ids
```

Then hook into `Orchestrator.step()`. In the `if proposal is None:` branch, after `_maybe_digest()` and `_maybe_code()`, add:

```python
from auto_qml import lab as _lab
closed = close_stale_campaigns(self.paths.runs_db, lab_id=_lab.LAB_ID)
if closed:
    notebook_append(
        self.paths.notebook,
        f"## {now_iso()} — force-closed stale campaigns: {closed}\n"
    )
```

- [ ] **Step 4: Run, verify force-close tests pass**

Run: `uv run pytest tests/test_force_close.py -v`
Expected: 2 passed.

- [ ] **Step 5: Write failing test for flat-digest counter**

`tests/test_flat_digest_counter.py`:

```python
"""Analyst updates digests_without_improvement in state.json based on
whether the new digest's best W1 improved over the previous."""
from __future__ import annotations

import json

import pytest

from agents.analyst import update_flat_digest_counter


def test_counter_resets_on_improvement():
    state = {"digests_without_improvement": 3, "last_digest_best_w1": 0.020}
    new = update_flat_digest_counter(state, current_best_w1=0.015, epsilon=0.005)
    assert new["digests_without_improvement"] == 0
    assert new["last_digest_best_w1"] == 0.015


def test_counter_increments_on_no_improvement():
    state = {"digests_without_improvement": 1, "last_digest_best_w1": 0.020}
    new = update_flat_digest_counter(state, current_best_w1=0.0205, epsilon=0.005)
    assert new["digests_without_improvement"] == 2


def test_counter_initialized_when_absent():
    state = {}
    new = update_flat_digest_counter(state, current_best_w1=0.020, epsilon=0.005)
    assert new["digests_without_improvement"] == 0
    assert new["last_digest_best_w1"] == 0.020


def test_handles_missing_current_w1():
    state = {"digests_without_improvement": 1, "last_digest_best_w1": 0.020}
    new = update_flat_digest_counter(state, current_best_w1=None, epsilon=0.005)
    # No data → counter unchanged
    assert new["digests_without_improvement"] == 1
```

- [ ] **Step 6: Run, verify failure**

Run: `uv run pytest tests/test_flat_digest_counter.py -v`
Expected: ImportError.

- [ ] **Step 7: Implement in `agents/analyst.py`**

Add to `agents/analyst.py`:

```python
def update_flat_digest_counter(
    state: dict, *, current_best_w1: float | None, epsilon: float
) -> dict:
    """Return a new state dict with `digests_without_improvement` and
    `last_digest_best_w1` updated based on this digest's current best W1.

    epsilon: absolute improvement threshold; a drop in W1 by more than
    epsilon counts as improvement (resets counter).
    """
    out = dict(state)
    if current_best_w1 is None:
        out.setdefault("digests_without_improvement", out.get("digests_without_improvement", 0))
        return out
    prev = out.get("last_digest_best_w1")
    if prev is None or (prev - current_best_w1) > epsilon:
        out["digests_without_improvement"] = 0
    else:
        out["digests_without_improvement"] = int(out.get("digests_without_improvement", 0)) + 1
    out["last_digest_best_w1"] = current_best_w1
    return out
```

Then in the existing `write_digest(...)` function, after the digest is produced and just before returning, compute the current best W1 across recent runs and call `update_flat_digest_counter`, persisting via `save_state`. (The implementer will need to look at what `recent_runs` returns; pull the minimum non-null `e_w1` across the window.)

- [ ] **Step 8: Run, verify all pass**

Run: `uv run pytest tests/test_flat_digest_counter.py tests/test_force_close.py -v`
Expected: 6 passed.

- [ ] **Step 9: Commit**

```bash
git add agents/orchestrator.py agents/analyst.py tests/test_force_close.py tests/test_flat_digest_counter.py
git commit -m "feat(orchestrator,analyst): 48h force-close + flat-digest counter"
```

---

## Task 10: Plumb campaign_id + researcher_mode into runs DB

**Files:**
- Modify: `auto_qml/run.py`, `agents/executor.py`, `agents/state.py`
- Create: `tests/test_run_columns.py`

- [ ] **Step 1: Extend `RUNS_SCHEMA` in `auto_qml/run.py`**

In `auto_qml/run.py`, modify the `RUNS_SCHEMA` constant. Add these two columns, just before the closing `);` of the `CREATE TABLE`:

```sql
    campaign_id         TEXT,
    researcher_mode     TEXT,
```

This way fresh DBs and migrated DBs have identical shape.

- [ ] **Step 2: Write the values into the row**

Find the INSERT INTO runs in `auto_qml/run.py` (the row-writing code path). Add `campaign_id` and `researcher_mode` to the column list and parameters list. Their values come from the YAML config under keys `run.campaign_id` and `run.researcher_mode`; both default to `None` when absent.

In `_open_db` or wherever the config dict is consumed for INSERTs, read `cfg.get("run", {}).get("campaign_id")` and `cfg.get("run", {}).get("researcher_mode")` and pass through as parameters.

- [ ] **Step 3: Update `recent_runs` SELECT**

In `agents/state.py`, modify the `recent_runs` SQL to include the new columns:

Add `campaign_id, researcher_mode` to the SELECT column list. Order does not matter for dict-returning row_factory.

- [ ] **Step 4: Modify `agents/executor.py`** to flow proposal fields into config

In `agents/executor.py`, locate where the proposal's `config_overrides` are merged into the YAML config sent to `auto_qml.run`. Add lines that inject:

```python
config_overrides = dict(proposal.get("config_overrides", {}))
if proposal.get("campaign_id"):
    config_overrides["run.campaign_id"] = proposal["campaign_id"]
if proposal.get("mode"):
    config_overrides["run.researcher_mode"] = proposal["mode"]
```

before the merge step.

- [ ] **Step 5: Write integration test**

`tests/test_run_columns.py`:

```python
"""campaign_id + researcher_mode get persisted into a row."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


@pytest.mark.slow
def test_columns_present_in_fresh_db(tmp_path):
    """A fresh runs.sqlite created by auto_qml.run includes the new columns."""
    # Use the smallest possible config to keep test cost minimal.
    repo = Path(__file__).parent.parent
    cfg = yaml.safe_load((repo / "config/default.yaml").read_text())
    cfg.setdefault("run", {})
    cfg["run"]["campaign_id"] = "c-test"
    cfg["run"]["researcher_mode"] = "refine"
    cfg["run"]["epochs"] = 1                 # smoke only
    cfg["run"]["eval_n"] = 10
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))

    lab = tmp_path / "lab"
    lab.mkdir()
    proc = subprocess.run(
        [sys.executable, "-m", "auto_qml.run", "--config", str(cfg_path),
         "--lab-dir", str(lab)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        pytest.skip(f"auto_qml.run unavailable in CI environment: {proc.stderr[:500]}")
    db = lab / "runs.sqlite"
    conn = sqlite3.connect(db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    assert "campaign_id" in cols
    assert "researcher_mode" in cols
    row = conn.execute(
        "SELECT campaign_id, researcher_mode FROM runs LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == ("c-test", "refine")
```

Note: this test runs the actual training pipeline at minimum config so it is slow. Mark as `@pytest.mark.slow` and run separately:

`uv run pytest tests/test_run_columns.py -v -m slow` (skip with `-m "not slow"`).

If `auto_qml.run` has no `--lab-dir` flag, the implementer should add one as part of this task (or set the env var the run module uses).

- [ ] **Step 6: Run the unit-level tests** (re-running full test suite)

Run: `uv run pytest tests/ -v -m "not slow"`
Expected: all green; the slow integration test is skipped.

- [ ] **Step 7: Run the slow integration test once locally**

Run: `uv run pytest tests/test_run_columns.py -v -m slow`
Expected: passes; row contains the new column values.

- [ ] **Step 8: Commit**

```bash
git add auto_qml/run.py agents/executor.py agents/state.py tests/test_run_columns.py
git commit -m "feat(db): persist campaign_id + researcher_mode into runs.sqlite"
```

---

## Task 11: Analyst groups digest by campaign

**Files:**
- Modify: `agents/analyst.py`, `agents/prompts/analyst.md`
- Create: `tests/test_analyst_grouping.py`

- [ ] **Step 1: Write failing test for grouping helper**

`tests/test_analyst_grouping.py`:

```python
"""Analyst groups recent runs by campaign_id for the digest prompt."""
from __future__ import annotations

import pytest

from agents.analyst import group_runs_by_campaign


def test_groups_runs_with_campaign_id():
    runs = [
        {"run_id": "r1", "campaign_id": "c1", "e_w1": 0.02},
        {"run_id": "r2", "campaign_id": "c1", "e_w1": 0.01},
        {"run_id": "r3", "campaign_id": "c2", "e_w1": 0.03},
    ]
    grouped = group_runs_by_campaign(runs)
    assert set(grouped.keys()) == {"c1", "c2"}
    assert len(grouped["c1"]) == 2
    assert len(grouped["c2"]) == 1


def test_runs_without_campaign_under_none_key():
    runs = [
        {"run_id": "r1", "campaign_id": None, "e_w1": 0.02},
        {"run_id": "r2", "campaign_id": "c1", "e_w1": 0.01},
    ]
    grouped = group_runs_by_campaign(runs)
    assert None in grouped
    assert len(grouped[None]) == 1


def test_empty_input():
    assert group_runs_by_campaign([]) == {}
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/test_analyst_grouping.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement helper in `agents/analyst.py`**

```python
def group_runs_by_campaign(runs: list[dict]) -> dict[str | None, list[dict]]:
    out: dict[str | None, list[dict]] = {}
    for r in runs:
        key = r.get("campaign_id")
        out.setdefault(key, []).append(r)
    return out
```

- [ ] **Step 4: Update digest prompt assembly to group**

In `agents/analyst.write_digest(...)`, before composing the prompt input from `recent_runs`, call `group_runs_by_campaign` and build a per-campaign block in the prompt's user message:

```python
groups = group_runs_by_campaign(recent_runs(paths.runs_db, n=60))
# Compose a section per campaign (load campaign rows via campaign_open_list +
# closed ones via a new helper or direct SQL). Render each as:
#   ### Campaign <id> — <question>
#   <table or list of N runs>
```

(The implementer may need to also fetch closed campaigns referenced in the recent-runs window; add a `campaign_get(db, id)` helper to `agents/state.py` if not present.)

- [ ] **Step 5: Update `agents/prompts/analyst.md`**

Append to the analyst prompt:

```markdown

## Campaign grouping

The user message groups recent runs by their `campaign_id`. Each
campaign block has the campaign's question + hypothesis hash. In your
digest, produce one short narrative section per campaign (no campaign
narrative for runs in the `None`/uncampaigned group beyond a short
"miscellaneous" note). Cross-campaign comparisons go in a final
"Synthesis" section.
```

- [ ] **Step 6: Verify grouping tests pass**

Run: `uv run pytest tests/test_analyst_grouping.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add agents/analyst.py agents/prompts/analyst.md tests/test_analyst_grouping.py
git commit -m "feat(analyst): group recent runs by campaign in digest"
```

---

## Task 12: Writer — frontmatter emission, body structure, novelty/gain gate

**Files:**
- Modify: `agents/writer.py`, `agents/prompts/writer.md`
- Create: `tests/test_writer_output.py`, `tests/test_novelty_gate.py`

- [ ] **Step 1: Add the novelty/gain gate helper test**

`tests/test_novelty_gate.py`:

```python
"""The Writer is only triggered when a campaign shows novelty + significant gain."""
from __future__ import annotations

import pytest

from agents.writer import should_publish, GateInputs


def test_below_threshold_blocks():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.0199,   # only 0.5% better
        novelty_claim="some claim",
        existing_lab_claims=[],
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert not ok
    assert "gain" in reason.lower()


def test_at_threshold_passes():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.018,   # 10% better
        novelty_claim="first lap-pyr UNet on QFM",
        existing_lab_claims=["amp-ratio gate", "annular radial head"],
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert ok, reason


def test_empty_novelty_blocks():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.010,
        novelty_claim="   ",
        existing_lab_claims=[],
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert not ok
    assert "novel" in reason.lower()


def test_duplicates_existing_claim_blocks():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.010,
        novelty_claim="amp-ratio gate",
        existing_lab_claims=["amp-ratio gate", "annular radial head"],
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert not ok
    assert "duplicate" in reason.lower() or "existing" in reason.lower()


def test_refutation_path_passes_without_gain():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.020,   # no gain
        novelty_claim="refutes prior corroborated claim X",
        existing_lab_claims=[],
        refutation_of_corroborated="claim-x",
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert ok
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/test_novelty_gate.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement gate in `agents/writer.py`**

Add to the top of `agents/writer.py`:

```python
from dataclasses import dataclass, field


@dataclass
class GateInputs:
    primary_metric_name: str
    baseline_value: float
    candidate_value: float
    novelty_claim: str
    existing_lab_claims: list[str] = field(default_factory=list)
    refutation_of_corroborated: str | None = None


def should_publish(
    inputs: GateInputs, *, gain_threshold: float = 0.05
) -> tuple[bool, str]:
    """Apply the novelty + significant-gain gate.

    Pass conditions (either is sufficient to satisfy the gain half):
      - candidate_value strictly better than baseline by at least
        gain_threshold (relative; lower-is-better metric assumed).
      - refutation_of_corroborated is set (refuting a previously-
        corroborated claim is publishable without gain).

    Novelty must always pass: non-empty stripped claim, not a duplicate
    of existing lab claims (case-insensitive exact match).
    """
    nov = inputs.novelty_claim.strip()
    if not nov:
        return (False, "novelty_claim is empty")
    if any(nov.lower() == c.strip().lower() for c in inputs.existing_lab_claims):
        return (False, f"novelty_claim duplicates existing lab claim: {nov!r}")

    if inputs.refutation_of_corroborated:
        return (True, "refutation path")

    if inputs.baseline_value <= 0:
        return (False, "non-positive baseline_value; cannot compute relative gain")
    rel = (inputs.baseline_value - inputs.candidate_value) / inputs.baseline_value
    if rel < gain_threshold:
        return (False, f"insufficient gain: {rel:.3%} < {gain_threshold:.1%}")

    return (True, f"gain={rel:.1%}, novelty OK")
```

- [ ] **Step 4: Run, verify gate tests pass**

Run: `uv run pytest tests/test_novelty_gate.py -v`
Expected: 5 passed.

- [ ] **Step 5: Write failing test for Writer output structure**

`tests/test_writer_output.py`:

```python
"""Writer emits valid frontmatter + the five required body sections."""
from __future__ import annotations

import yaml

import pytest

from agents.writer import compose_paper
from auto_qml.schemas.paper_frontmatter import (
    PaperFrontmatter,
    REQUIRED_SECTIONS_IN_ORDER,
    structural_check,
)


def test_compose_paper_returns_valid_artifact(fake_anthropic_factory):
    body_md = "\n".join(
        f"## {s}\n\nSome content for {s}.\n" for s in REQUIRED_SECTIONS_IN_ORDER
    )
    client = fake_anthropic_factory([body_md])
    artifact = compose_paper(
        client=client,
        campaign={
            "id": "c-1",
            "question": "does X help?",
            "hypothesis_path": "popper-corpus/c1/hypothesis.md",
            "hypothesis_hash": "sha256:" + "0" * 64,
        },
        metric_provenance=[
            {
                "name": "e_w1",
                "value": 0.012,
                "delta_vs_baseline": -0.004,
                "runs": ["r1"],
                "seeds": [0, 1, 2],
            }
        ],
        novelty_claim="first lap-pyr UNet on QFM",
        code_sha="abcdef1",
        code_repo="https://github.com/mashathepotato/auto-qml",
    )
    assert artifact.startswith("---")
    # split frontmatter / body
    _, fm_yaml, body = artifact.split("---", 2)
    fm = yaml.safe_load(fm_yaml)
    PaperFrontmatter(**fm)  # raises on invalid
    ok, errors = structural_check(body)
    assert ok, errors


def test_compose_paper_fails_loud_when_body_missing_section(fake_anthropic_factory):
    bad_body = "## Motivation\n\nfoo\n\n## Results\n\nbar\n"
    client = fake_anthropic_factory([bad_body])
    with pytest.raises(ValueError, match="missing required section"):
        compose_paper(
            client=client,
            campaign={
                "id": "c-1",
                "question": "q",
                "hypothesis_path": "popper-corpus/c1/hypothesis.md",
                "hypothesis_hash": "sha256:" + "0" * 64,
            },
            metric_provenance=[
                {
                    "name": "e_w1",
                    "value": 0.012,
                    "delta_vs_baseline": -0.004,
                    "runs": ["r1"],
                    "seeds": [0],
                }
            ],
            novelty_claim="x",
            code_sha=None,
            code_repo=None,
        )


def test_compose_paper_allows_omitted_code_pointers(fake_anthropic_factory):
    body_md = "\n".join(
        f"## {s}\n\nContent.\n" for s in REQUIRED_SECTIONS_IN_ORDER
    )
    client = fake_anthropic_factory([body_md])
    artifact = compose_paper(
        client=client,
        campaign={
            "id": "c-1",
            "question": "q",
            "hypothesis_path": "popper-corpus/c1/hypothesis.md",
            "hypothesis_hash": "sha256:" + "0" * 64,
        },
        metric_provenance=[
            {"name": "e_w1", "value": 0.012, "delta_vs_baseline": -0.004,
             "runs": ["r1"], "seeds": [0]},
        ],
        novelty_claim="prose-only artifact",
        code_sha=None,
        code_repo=None,
    )
    _, fm_yaml, _ = artifact.split("---", 2)
    fm = yaml.safe_load(fm_yaml)
    assert fm["code_repo"] is None and fm["code_sha"] is None
```

- [ ] **Step 6: Run, verify failures**

Run: `uv run pytest tests/test_writer_output.py -v`
Expected: ImportError on `compose_paper`.

- [ ] **Step 7: Implement `compose_paper` in `agents/writer.py`**

Add to `agents/writer.py`:

```python
import yaml as _yaml
from datetime import date as _date

from auto_qml import lab as _lab
from auto_qml.schemas.paper_frontmatter import (
    PaperFrontmatter,
    REQUIRED_SECTIONS_IN_ORDER,
    structural_check,
)


_WRITER_SYSTEM = """You are the Writer agent for an autonomous research lab.
You produce agent-readable paper artifacts (Markdown) for OTHER agents to read.
Output ONLY the body Markdown — five sections in this exact order:

""" + "\n".join(f"## {s}" for s in REQUIRED_SECTIONS_IN_ORDER) + """

Methods must be detailed enough that another lab's Researcher can draft
a recreation config WITHOUT consulting the source repo. Use inline code
blocks where the canonical implementation is non-obvious.

No frontmatter — the caller adds that. No code fences around the
output. Begin with the literal line "## Motivation"."""


def compose_paper(
    *,
    client,
    campaign: dict,
    metric_provenance: list[dict],
    novelty_claim: str,
    code_sha: str | None,
    code_repo: str | None,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 8192,
) -> str:
    """Produce a complete platform-shaped paper artifact.

    Returns the artifact as a string (YAML frontmatter + body).
    Raises ValueError if the body fails structural check or the
    frontmatter fails pydantic validation.
    """
    user = (
        f"Campaign: {campaign['id']} — {campaign['question']}\n"
        f"Hypothesis file: {campaign['hypothesis_path']}\n"
        f"Hypothesis hash: {campaign['hypothesis_hash']}\n"
        f"Metrics: {metric_provenance}\n"
        f"Novelty: {novelty_claim}\n"
        f"Write the paper body now."
    )
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_WRITER_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    body = "".join(b.text for b in response.content).strip()
    ok, errors = structural_check(body)
    if not ok:
        raise ValueError("Writer body failed structural check: " + "; ".join(errors))

    fm = PaperFrontmatter(
        lab_id=_lab.LAB_ID,
        domain=_lab.DOMAIN,
        subdomain=_lab.SUBDOMAIN,
        pi_handle=_lab.PI_HANDLE,
        campaign_id=campaign["id"],
        hypothesis_hash=campaign["hypothesis_hash"],
        hypothesis_path=campaign["hypothesis_path"],
        code_repo=code_repo,
        code_sha=code_sha,
        metric_provenance=metric_provenance,
        novelty_claim=novelty_claim,
        published_at=_date.today().isoformat(),
        status="preprint",
    )
    fm_yaml = _yaml.safe_dump(fm.model_dump(), sort_keys=False).strip()
    return f"---\n{fm_yaml}\n---\n\n{body}\n"
```

- [ ] **Step 8: Run, verify writer-output tests pass**

Run: `uv run pytest tests/test_writer_output.py -v`
Expected: 3 passed.

- [ ] **Step 9: Update `agents/prompts/writer.md`**

Append to `agents/prompts/writer.md`:

```markdown

## Output discipline (Phase A)

The Writer's job is to produce **agent-readable paper artifacts** —
Markdown for other agents in other labs to read and recreate from.
This is NOT a human-targeted PDF; do not concern yourself with
typesetting, figures, or LaTeX.

Required body sections, in order:

1. `## Motivation`
2. `## Methods` (complete enough to recreate without source code)
3. `## Results` (quantitative; cite runs by uuid)
4. `## Conclusion` (corroborate / refute / inconclusive vs the hypothesis falsifier)
5. `## Next questions`

A separate caller adds YAML frontmatter and applies the novelty + gain
gate. Your job is the body.
```

- [ ] **Step 10: Wire `should_publish` + `compose_paper` into the existing Writer entry point**

Locate the existing top-level Writer function (likely `write_paper` or `draft` in `agents/writer.py`). Update it to:

1. Compute primary-metric baseline + candidate from the campaign's runs (likely best e_w1 of the baseline campaign vs best e_w1 of this campaign).
2. Look up existing lab claims (read previously-written papers' frontmatter `novelty_claim` fields; or skip this and pass `[]` if no prior corpus directory).
3. Call `should_publish(GateInputs(...))`. If `(False, reason)`, log to notebook, close the campaign with `close_reason="no novel publishable result"` (use `campaign_close`), do NOT call `compose_paper`.
4. If `(True, _)`, call `compose_paper(...)`, write the artifact to `paper/<campaign_id>-<slug>.md`, log to notebook, return.

- [ ] **Step 11: Run full suite**

Run: `uv run pytest tests/ -v -m "not slow"`
Expected: all green.

- [ ] **Step 12: Commit**

```bash
git add agents/writer.py agents/prompts/writer.md tests/test_writer_output.py tests/test_novelty_gate.py
git commit -m "feat(writer): platform-shaped artifact + novelty/gain gate"
```

---

## Task 13: Apply migration at orchestrator startup

**Files:**
- Modify: `agents/__main__.py`

- [ ] **Step 1: Add migration call at startup**

In `agents/__main__.py`, find the entry point that constructs the `Orchestrator` (or where `init_lab` is called). Immediately after `init_lab(paths)`, add:

```python
from auto_qml.migrations.runner import apply_campaigns_migration
apply_campaigns_migration(paths.runs_db)
```

- [ ] **Step 2: Smoke-verify by running the orchestrator's dry-run**

Run: `uv run python -m agents --dry-run --max-iterations 1` (or whichever flag the existing `__main__.py` exposes).

Expected: starts, applies migration (idempotent if already applied), exits cleanly.

- [ ] **Step 3: Verify migration columns present in the live lab DB**

Run (manually):
```bash
sqlite3 lab/runs.sqlite "PRAGMA table_info(runs);" | grep -E "campaign_id|researcher_mode"
sqlite3 lab/runs.sqlite "SELECT name FROM sqlite_master WHERE type='table';" | grep campaigns
```
Expected: both `campaign_id` / `researcher_mode` shown; `campaigns` table listed.

- [ ] **Step 4: Commit**

```bash
git add agents/__main__.py
git commit -m "feat(orchestrator): apply campaigns migration at startup"
```

---

## Task 14: End-to-end smoke + final integration check

**Files:**
- Run only; no code changes.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest tests/ -v`
Expected: all green. Slow test will run if not filtered.

- [ ] **Step 2: Run linter**

Run: `uv run ruff check agents/ auto_qml/ tests/`
Expected: clean (or only warnings the implementer agrees to ignore).

- [ ] **Step 3: Spot-check that the orchestrator still starts and produces a Researcher proposal**

```bash
# In a separate terminal — DON'T point at the live lab/.
uv run python -m agents --lab-dir /tmp/auto-qml-smoke --max-iterations 1 --dry-run
```

Expected: notebook entry shows "Researcher mode: refine (flat_digests=0, override=None)"; no errors.

- [ ] **Step 4: Live integration smoke (with real API, low budget)**

Set a budget cap of ~$1 and let the orchestrator run for one full step against a `/tmp/auto-qml-smoke/` lab dir. Confirm:

- A campaign opens (or doesn't, depending on Researcher output)
- If it opens: `popper-corpus/<slug>/hypothesis.md` exists, validates
- A proposal lands on the queue with `mode` and `campaign_id` set
- One run executes, writes a row with the new columns populated
- If a digest fires, it groups by campaign

Compare against the spec's verification section. Note any divergences in a follow-up task.

- [ ] **Step 5: Final commit + tag**

```bash
git tag -a phase-a-complete -m "Phase A: lab foundation (modes + campaigns + popper-gate + paper artifacts)"
```

---

## Self-Review Notes

**Spec coverage check:**

- §1 Researcher modes — Task 6 (plumbing), Task 7 (selector + override). ✓
- §2 Campaigns — Task 2 (schema + helpers), Task 8 (open path), Task 9 (force-close), Task 10 (DB plumbing), Task 11 (digest grouping). ✓
- §3 Popper Probe gate — Task 5 (gate impl), Task 8 (researcher integration). ✓
- §4 Lab identity stub — Task 3. ✓
- §5 Agent-readable paper artifact — Task 4 (schema + structural validator), Task 12 (writer compose + gate). ✓
- Schema migration — Task 2 (sql + runner), Task 13 (startup application). ✓
- Verification items from spec — covered across Tasks 2, 6, 7, 8, 9, 10, 12 plus the integration smoke in Task 14.

**No placeholders / "implement later" / generic-handle-X language.** All steps show concrete code or commands.

**Type consistency:** `GateResult`, `GateInputs`, `PaperFrontmatter`, `MetricProvenance`, `campaign_insert`, `campaign_close`, `campaign_open_list`, `campaign_stale_open`, `close_stale_campaigns`, `select_mode`, `read_force_mode`, `should_publish`, `compose_paper`, `run_gate`, `apply_campaigns_migration`, `group_runs_by_campaign`, `update_flat_digest_counter` — each declared once, used consistently across tasks.

**Known follow-ups outside Phase A scope (documented in spec):** pluggable runners, journal platform itself, replication mechanics, multi-lab orchestration, manual verification of cache-hit-rate > 70% (cannot test in-line; left for the Task 14 live smoke).
