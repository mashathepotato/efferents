"""efferents CLI entry point.

  efferents validate --submission <dir>
  efferents start    --submission <dir> [--detach] [--lab-root <path>]
  efferents status   [--lab-id <id>]
  efferents stop     --lab-id <id>
  efferents list

The `main(argv=None)` entry point is exposed for tests; pyproject.toml
console_scripts will point at `efferents.cli:main` (Task 16).
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from efferents import daemon
from efferents import lab as lab_mod
from efferents.envfile import load_dotenv
from efferents.lab import LabConfig, SubmissionError
from efferents.registry import LabRecord, Registry


def _cmd_validate(args: argparse.Namespace) -> int:
    sub = Path(args.submission).resolve()
    try:
        cfg = LabConfig.from_submission(sub)
    except SubmissionError as e:
        print(f"validation failed: {e}", file=sys.stderr)
        return 1
    print(f"OK lab_id={cfg.lab_id} domain={cfg.domain} source_dir={cfg.source.dir}")
    return 0


def _orchestrator_loop() -> None:
    # Indirection so tests can monkey-patch the loop body without forking.
    # In production, builds an Orchestrator from the active LabConfig and
    # runs it. The orchestrator import is deferred to avoid pulling heavy
    # transitive deps at CLI startup.
    from efferents.agents import orchestrator  # noqa: PLC0415
    cfg = lab_mod.get_config()
    o = orchestrator.Orchestrator(
        lab_dir="lab",
        context_dir="context",
        daily_cap_usd=cfg.budget.daily_cap_usd,
        dry_run=False,
        startup_message=f"efferents daemon for lab_id={cfg.lab_id}",
    )
    o.run()


def _init_lab_root(submission_dir: Path, lab_root: Path) -> None:
    """Create lab/ dir + run migrations + copy provenance files."""
    lab_root.mkdir(parents=True, exist_ok=True)
    (lab_root / "progress").mkdir(exist_ok=True)
    (lab_root / "papers").mkdir(exist_ok=True)

    shutil.copy2(submission_dir / "hypothesis.md", lab_root / "hypothesis.md")
    shutil.copy2(submission_dir / "lab.yaml", lab_root / "lab.yaml")

    state_json = lab_root / "state.json"
    if not state_json.exists():
        state_json.write_text("{}")

    from efferents.migrations.runner import (  # noqa: PLC0415
        apply_campaigns_migration,
        ensure_runs_table,
    )
    apply_campaigns_migration(lab_root / "runs.sqlite")
    ensure_runs_table(lab_root / "runs.sqlite", lab_mod.get_config())

    context_dir = submission_dir / "context"
    context_dir.mkdir(exist_ok=True)
    research_log = context_dir / "research_log.md"
    if not research_log.exists():
        cfg = lab_mod.get_config()
        research_log.write_text(
            f"# {cfg.lab_id} research log\n\n"
            "*(empty — populate to guide the Researcher; "
            "the lab will operate from the hypothesis if left blank)*\n"
        )


def _cmd_start(args: argparse.Namespace) -> int:
    sub = Path(args.submission).resolve()
    try:
        cfg = LabConfig.from_submission(sub)
    except SubmissionError as e:
        print(f"validation failed: {e}", file=sys.stderr)
        return 1

    lab_root = Path(args.lab_root).resolve() if args.lab_root else (sub / "lab").resolve()

    # Load the submission's .env (if any) so the daemon — including a detached
    # child, which inherits this process's os.environ — can resolve
    # ANTHROPIC_API_KEY without it being exported in the launching shell.
    load_dotenv(sub / ".env")

    lab_mod.set_config(cfg)
    _init_lab_root(sub, lab_root)
    os.chdir(sub)

    started_at = datetime.now(timezone.utc).isoformat()
    reg = Registry()
    reg.register(LabRecord(
        lab_id=cfg.lab_id,
        submission_dir=str(sub),
        lab_root=str(lab_root),
        pid=os.getpid(),
        started_at=started_at,
        status="running",
    ))

    print(f"lab_id={cfg.lab_id} pid={os.getpid()} dashboard={lab_root}/progress/index.html")

    if args.detach:
        child_pid = daemon.daemonize_and_run(lab_root, _orchestrator_loop)
        rec = reg.get(cfg.lab_id)
        if rec is not None:
            rec.pid = child_pid
            reg.register(rec)  # idempotent replace
        return 0

    try:
        daemon.run_foreground(lab_root, _orchestrator_loop)
    finally:
        reg.update_status(cfg.lab_id, "stopped")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    reg = Registry()
    records = reg.list()
    if not records:
        print("no labs registered")
        return 0
    print(f"{'LAB_ID':<24} {'STATUS':<10} {'STARTED':<25} SUBMISSION")
    for r in records:
        status = r.status
        if status == "running" and not daemon.is_pid_alive(r.pid):
            status = "crashed"
        print(f"{r.lab_id:<24} {status:<10} {r.started_at:<25} {r.submission_dir}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    reg = Registry()
    if args.lab_id is None:
        return _cmd_list(args)
    rec = reg.get(args.lab_id)
    if rec is None:
        print(f"unknown lab_id: {args.lab_id}", file=sys.stderr)
        return 1

    alive = daemon.is_pid_alive(rec.pid)
    status = rec.status
    if rec.status == "running" and not alive:
        status = "crashed"
        reg.update_status(args.lab_id, "crashed")

    lab_root = Path(rec.lab_root)
    print(f"lab_id={rec.lab_id}")
    print(f"status={status}")
    print(f"started_at={rec.started_at}")
    print(f"pid={rec.pid} (alive={alive})")
    state_json = lab_root / "state.json"
    if state_json.exists():
        mtime = datetime.fromtimestamp(state_json.stat().st_mtime, tz=timezone.utc).isoformat()
        print(f"last_activity={mtime}")
    print(f"dashboard=file://{lab_root}/progress/index.html")
    halt = lab_root / "halt_reason.txt"
    if halt.exists():
        print(f"halt_reason={halt.read_text().strip()}")
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    reg = Registry()
    rec = reg.get(args.lab_id)
    if rec is None:
        print(f"unknown lab_id: {args.lab_id}", file=sys.stderr)
        return 1

    if daemon.is_pid_alive(rec.pid):
        os.kill(rec.pid, signal.SIGTERM)
        for _ in range(100):
            if not daemon.is_pid_alive(rec.pid):
                break
            time.sleep(0.1)
        if daemon.is_pid_alive(rec.pid):
            os.kill(rec.pid, signal.SIGKILL)
            print(f"warning: SIGTERM ignored, sent SIGKILL to PID {rec.pid}", file=sys.stderr)

    reg.update_status(args.lab_id, "stopped")
    print(f"stopped lab_id={args.lab_id}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from efferents.dashboard import server as dash_server

    lab_root = Path(args.lab_root).resolve()
    try:
        cfg = LabConfig.from_submission(lab_root)
    except SubmissionError as e:
        print(f"could not load lab config from {lab_root}: {e}", file=sys.stderr)
        return 1
    lab_mod.set_config(cfg)
    dash_server.serve(lab_root, port=args.port, open_browser=not args.no_open)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="efferents")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate", help="Validate a submission directory")
    p_validate.add_argument("--submission", required=True)
    p_validate.set_defaults(func=_cmd_validate)

    p_start = sub.add_parser("start", help="Start the lab daemon")
    p_start.add_argument("--submission", required=True)
    p_start.add_argument("--detach", action="store_true")
    p_start.add_argument("--lab-root", default=None)
    p_start.set_defaults(func=_cmd_start)

    p_status = sub.add_parser("status", help="Show lab status")
    p_status.add_argument("--lab-id", default=None)
    p_status.set_defaults(func=_cmd_status)

    p_stop = sub.add_parser("stop", help="Stop a running lab daemon")
    p_stop.add_argument("--lab-id", required=True)
    p_stop.set_defaults(func=_cmd_stop)

    p_list = sub.add_parser("list", help="List all registered labs")
    p_list.set_defaults(func=_cmd_list)

    p_serve = sub.add_parser("serve", help="Start the read-only web dashboard")
    p_serve.add_argument("--lab-root", default="lab")
    p_serve.add_argument("--port", type=int, default=8800)
    p_serve.add_argument("--no-open", action="store_true",
                         help="Do not auto-open the browser")
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
