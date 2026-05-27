"""The 24/7 loop. Researcher refills the queue; Executor drains it; Analyst writes
periodic digests and pushes notifications.

Restart-safe: all state lives in lab/. On startup, we just resume.

Stopping: send SIGTERM (or Ctrl-C interactively); the loop exits cleanly between
iterations. If killed mid-run, the current proposal is lost from the queue but
nothing is corrupted.
"""
from __future__ import annotations

import signal
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import re as _re

import anthropic

from efferents.agents import analyst, coder, executor, researcher
from efferents.agents.budget import BudgetTracker
from efferents.agents.notify import notify_all
from efferents.agents.state import (
    LabPaths,
    StudentStateView,
    campaign_close,
    campaign_stale_open,
    init_lab,
    lab_paths,
    load_state,
    notebook_append,
    queue_pop,
    queue_push,
    queue_size,
    runs_count,
    save_state,
    now_iso,
)
from efferents import lab as _lab
from efferents.exec import RunResult, _run_and_capture
from efferents.migrations.runner import apply_campaigns_migration

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


def close_stale_campaigns(db_path: Path, *, lab_id: str, hours: float = 48.0) -> list[str]:
    stale = campaign_stale_open(db_path, lab_id, hours=hours)
    ids = [c["id"] for c in stale]
    for cid in ids:
        campaign_close(db_path, cid, reason="stale")
    return ids


def _hours_since(iso_ts: str | None) -> float:
    if not iso_ts:
        return 1e9
    try:
        t = datetime.fromisoformat(iso_ts)
    except ValueError:
        return 1e9
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def _seconds_until_next_utc_day() -> float:
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return (midnight - now).total_seconds()


class Orchestrator:
    def __init__(
        self,
        *,
        lab_dir: str | Path = "lab",
        context_dir: str | Path = "context",
        daily_cap_usd: float = 100.0,
        runs_per_digest: int = 40,
        hours_per_digest: float = 4.0,
        runs_per_coder: int = 8,
        hours_per_coder: float = 6.0,
        dry_run: bool = False,
        startup_message: str | None = None,
    ):
        self.paths: LabPaths = lab_paths(lab_dir)
        init_lab(self.paths)
        apply_campaigns_migration(self.paths.runs_db)
        self.context_dir = Path(context_dir)
        self.budget = BudgetTracker(self.paths.budget, daily_cap_usd=daily_cap_usd)
        self.runs_per_digest = runs_per_digest
        self.hours_per_digest = hours_per_digest
        self.runs_per_coder = runs_per_coder
        self.hours_per_coder = hours_per_coder
        self.dry_run = dry_run
        self._stop = False
        # Set to True after a successful Coder commit. The wrapper script
        # observes the special exit code and re-spawns the process so
        # auto_qml's modules are reloaded fresh from disk.
        self.restart_requested = False

        self.client: anthropic.Anthropic | None = None
        if not dry_run:
            self.client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        if startup_message:
            notebook_append(self.paths.notebook, f"## {now_iso()} — orchestrator start\n\n{startup_message}\n")
            # Suppress the "started" push when we're respawning right after a
            # Coder commit (the user just got the "code committed" push 2s ago;
            # they don't need a "started" follow-up).
            state = load_state(self.paths.state)
            last_coder = state.get("last_coder_ts")
            if not last_coder or _hours_since(last_coder) > 0.05:  # >3 minutes
                notify_all(title="auto-qml started", message=startup_message)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        self._stop = True
        notebook_append(self.paths.notebook, f"## {now_iso()} — received signal {signum}, stopping\n")

    def _next_student_id(self) -> str:
        """Round-robin: pick the next student to work on, advancing the cursor.

        Lives in state.json under `_global.current_student_idx` so it
        survives orchestrator restarts. With STUDENTS=[primary] (default),
        this always returns 'primary' and behavior matches single-student.
        """
        ids = _lab.student_ids()
        if not ids:
            return _lab.DEFAULT_STUDENT_ID
        if len(ids) == 1:
            return ids[0]
        state = load_state(self.paths.state)
        global_state = state.setdefault("_global", {})
        idx = int(global_state.get("current_student_idx", -1))
        idx = (idx + 1) % len(ids)
        global_state["current_student_idx"] = idx
        save_state(self.paths.state, state)
        return ids[idx]

    def _refill_queue(self) -> int:
        if queue_size(self.paths.queue) > 0:
            return 0
        if self.dry_run:
            # Hardcoded probe proposal so the loop is exercisable without API calls.
            queue_push(
                self.paths.queue,
                {
                    "name": f"dryrun_{datetime.now(timezone.utc).strftime('%H%M%S')}",
                    "hypothesis": "Dry-run probe: pipeline only.",
                    "expected": "metrics arbitrary",
                    "config_overrides": {"run.seed": 123, "run.model": "qfm"},
                },
            )
            return 1
        if self.budget.should_pause():
            self._sleep_paused("daily cap reached; refill skipped")
            return 0
        # Skip Researcher only on FRESH Coder backlog (≤2h since last
        # Researcher call). Original concern: saturation-driven rounds emit
        # architectural-only output and re-calling Researcher right after
        # spins lit_review at ~$2/iter. But an accumulating backlog (Coder
        # drains 1/6h, Researcher emits N/call) would permanently starve the
        # executor without this time bound.
        state = load_state(self.paths.state)
        # Choose which student gets this Researcher pass (round-robin across
        # _lab.STUDENTS). With one student configured, picks 'primary' every
        # time and behavior matches single-student.
        student_id = self._next_student_id()
        sstate = StudentStateView(state, student_id)
        if (
            _hours_since(sstate.get("last_researcher_ts")) < 2.0
            and coder.select_pending_proposal(paths=self.paths, student_id=student_id) is not None
        ):
            return 0
        override = read_force_mode(self.context_dir)
        mode = select_mode(state, override=override)
        notebook_append(
            self.paths.notebook,
            f"## {now_iso()} — Researcher mode: {mode} student={student_id} "
            f"(flat_digests={state.get('digests_without_improvement', 0)}, override={override})\n"
        )
        result = researcher.propose(
            paths=self.paths,
            context_dir=self.context_dir,
            budget=self.budget,
            client=self.client,
            mode=mode,
            student_id=student_id,
        )
        proposals = result.get("proposals", [])
        if not proposals:
            err = result.get("error")
            notebook_append(
                self.paths.notebook,
                f"## {now_iso()} — Researcher returned no proposals. Error: {err}\n\n"
                f"Raw: ```{result.get('raw', '')[:500]}```\n",
            )
            return 0
        for p in proposals:
            queue_push(self.paths.queue, p)
        return len(proposals)

    def _maybe_digest(self) -> None:
        state = load_state(self.paths.state)
        n_runs = runs_count(self.paths.runs_db)
        last_runs = int(state.get("last_digest_runs", 0))
        last_ts = state.get("last_digest_ts")
        runs_since = n_runs - last_runs
        hours_since = _hours_since(last_ts)
        if runs_since < self.runs_per_digest and hours_since < self.hours_per_digest:
            return

        if self.dry_run:
            notebook_append(self.paths.notebook, f"## {now_iso()} — digest skipped (dry-run)\n")
            state["last_digest_runs"] = n_runs
            state["last_digest_ts"] = now_iso()
            save_state(self.paths.state, state)
            return

        try:
            res = analyst.write_digest(
                paths=self.paths,
                context_dir=self.context_dir,
                budget=self.budget,
                client=self.client,
            )
            state["last_digest_runs"] = n_runs
            state["last_digest_ts"] = now_iso()
            state["last_digest_path"] = res["path"]
            save_state(self.paths.state, state)
        except Exception as e:
            notebook_append(
                self.paths.notebook, f"## {now_iso()} — digest FAILED: {type(e).__name__}: {e}\n"
            )

    def _sleep_paused(self, reason: str) -> None:
        secs = _seconds_until_next_utc_day()
        notebook_append(self.paths.notebook, f"## {now_iso()} — pausing: {reason}. Sleeping {secs/3600:.1f}h.\n")
        notify_all(title="auto-qml paused", message=reason)
        # Sleep in 60-second chunks so SIGTERM/SIGINT can interrupt.
        end = time.monotonic() + secs
        while not self._stop and time.monotonic() < end:
            time.sleep(min(60, max(1.0, end - time.monotonic())))

    def _maybe_code(self) -> None:
        if self.dry_run or self.client is None:
            return
        state = load_state(self.paths.state)
        n_runs = runs_count(self.paths.runs_db)
        # Walk students in declaration order looking for one whose Coder is
        # due and has a pending backlog. With one student, this collapses
        # to the legacy behavior.
        for sid in _lab.student_ids():
            sstate = StudentStateView(state, sid)
            last_runs = int(sstate.get("last_coder_runs", 0))
            last_ts = sstate.get("last_coder_ts")
            if (n_runs - last_runs) < self.runs_per_coder and _hours_since(last_ts) < self.hours_per_coder:
                continue
            if self.budget.should_pause():
                return
            proposal = coder.select_pending_proposal(paths=self.paths, student_id=sid)
            if proposal is None:
                # Bump cursor anyway so we don't recheck this student every iteration.
                sstate["last_coder_runs"] = n_runs
                sstate["last_coder_ts"] = now_iso()
                save_state(self.paths.state, state)
                continue
            student_id = sid
            break
        else:
            # No student had pending work.
            return
        try:
            result = coder.implement_proposal(
                proposal=proposal,
                paths=self.paths,
                budget=self.budget,
                client=self.client,
            )
            sstate["last_coder_runs"] = n_runs
            sstate["last_coder_ts"] = now_iso()
            save_state(self.paths.state, state)
            if result.ok:
                notify_all(
                    title="auto-qml: code committed",
                    message=f"{result.name}: {result.summary or ''} ({result.commit_sha}) — orchestrator restarting to load new code",
                )
                # Trigger a self-restart so the running process picks up the
                # newly-committed code on next start.
                self.restart_requested = True
                self._stop = True
                notebook_append(
                    self.paths.notebook,
                    f"## {now_iso()} — Coder committed; orchestrator self-restart requested\n",
                )
        except Exception as e:
            notebook_append(
                self.paths.notebook,
                f"## {now_iso()} — Coder step FAILED: {type(e).__name__}: {e}\n",
            )

    def step(self) -> dict[str, Any]:
        """One iteration. Returns telemetry dict.

        Coder + digest cadence are checked every step, even when the queue is
        empty — otherwise architectural-only Researcher outputs (saturation-aware
        pivot) starve the loop: the executor has nothing to run, and the Coder
        never gets called to drain proposed_changes.md.
        """
        n_added = self._refill_queue()
        proposal = queue_pop(self.paths.queue)
        if proposal is None:
            # No config proposal to execute. Still fire digest + coder cadence;
            # if the Researcher just produced architectural proposals, the Coder
            # should pick them up rather than waiting for a run that won't come.
            self._maybe_digest()
            self._maybe_code()
            closed = close_stale_campaigns(self.paths.runs_db, lab_id=_lab.LAB_ID)
            if closed:
                notebook_append(
                    self.paths.notebook,
                    f"## {now_iso()} — force-closed stale campaigns: {closed}\n"
                )
            # Longer sleep when the queue stayed empty — slows the Researcher
            # spin-pump on saturation-driven architectural-only rounds.
            time.sleep(60)
            return {"event": "no_proposal", "added": n_added}
        outcome = executor.execute(paths=self.paths, proposal=proposal)
        self._maybe_digest()
        self._maybe_code()
        return {"event": "ran", "added": n_added, "outcome_ok": outcome.get("ok"), "name": outcome.get("name")}

    def run(self, *, max_iterations: int | None = None) -> None:
        i = 0
        while not self._stop:
            if max_iterations is not None and i >= max_iterations:
                break
            try:
                self.step()
            except Exception as e:
                notebook_append(
                    self.paths.notebook,
                    f"## {now_iso()} — orchestrator step FAILED: {type(e).__name__}: {e}\n",
                )
                # Cool-off then continue.
                time.sleep(60)
            i += 1
        notebook_append(self.paths.notebook, f"## {now_iso()} — orchestrator stopped after {i} iters\n")
        # Don't push "stopped" if we're just restarting for a Coder commit —
        # the user already got "code committed; restarting" 2s ago.
        if not self.restart_requested:
            notify_all(title="auto-qml stopped", message=f"orchestrator exited after {i} iterations")


def _execute_run(config_path: Path) -> RunResult:
    """Render the lab's run_command and execute it, parsing stdout JSON."""
    cfg = _lab.get_config()
    cmd = cfg.executor.run_command.format(config_path=str(config_path))
    return _run_and_capture(
        cmd,
        timeout_s=cfg.executor.run_timeout_s,
        cwd=str(cfg.source.dir),
        env_passthrough=cfg.executor.env_passthrough,
    )


def _persist_run_result(result: RunResult, run_id: str, config_path: Path) -> None:
    """Insert a row into lab/state.db from a RunResult.

    Skips when result.metrics is None (failed run with no parseable metrics).
    Tolerates columns that don't exist in the runs table by warning.
    """
    if not result.metrics:
        return
    db_path = Path("lab/state.db")
    cols = ["run_id", "started_at", "ended_at", "config_path"]
    now_iso = datetime.now(timezone.utc).isoformat()
    vals: list = [run_id, now_iso, now_iso, str(config_path)]
    for k, v in result.metrics.items():
        cols.append(k)
        vals.append(v)
    if result.git_commit:
        cols.append("git_commit")
        vals.append(result.git_commit)
    if result.elapsed_s is not None:
        cols.append("duration_seconds")
        vals.append(result.elapsed_s)
    placeholders = ",".join("?" for _ in vals)
    col_list = ",".join(cols)
    with sqlite3.connect(db_path) as conn:
        try:
            conn.execute(f"INSERT INTO runs ({col_list}) VALUES ({placeholders})", vals)
            conn.commit()
        except sqlite3.OperationalError as e:
            print(f"warning: could not persist metric row: {e}")
