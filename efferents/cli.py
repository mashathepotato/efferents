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
import sys
from datetime import datetime, timezone
from pathlib import Path

from efferents import daemon
from efferents import lab as lab_mod
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
    """Indirection so tests can monkey-patch the loop body without forking.
    In production, calls efferents.agents.orchestrator.start().

    NOTE: the import of orchestrator is intentionally deferred to avoid
    eagerly pulling in heavy transitive dependencies at CLI startup. This
    is a deliberate exception to the "all imports at top" rule.
    """
    from efferents.agents import orchestrator  # noqa: PLC0415
    orchestrator.start()


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

    from efferents.migrations import runner as _mig  # noqa: PLC0415
    _mig.apply_campaigns_migration(lab_root / "state.db")


def _cmd_start(args: argparse.Namespace) -> int:
    sub = Path(args.submission).resolve()
    try:
        cfg = LabConfig.from_submission(sub)
    except SubmissionError as e:
        print(f"validation failed: {e}", file=sys.stderr)
        return 1

    lab_root = Path(args.lab_root).resolve() if args.lab_root else (sub / "lab").resolve()
    _init_lab_root(sub, lab_root)

    lab_mod.set_config(cfg)
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


def main(argv: list[str] | None = None) -> int:
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
