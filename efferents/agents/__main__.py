"""CLI for the agent loop:

    python -m agents start              # run the loop forever
    python -m agents start --dry-run    # exercise loop with hardcoded proposals
    python -m agents start --max 3      # stop after N iterations (smoke)
    python -m agents propose-once       # one Researcher call, print proposals
    python -m agents digest-now         # force one Analyst digest
    python -m agents write-once         # one Writer pass (paper + slides)
    python -m agents start-writer       # continuous loop: writer fires when new runs land
    python -m agents status             # print recent runs + budget snapshot

Defaults assume cwd = repo root (lab/, context/, config/ relative).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

from efferents.agents import analyst, coder, researcher, writer
from efferents.agents.budget import BudgetTracker
from efferents.agents.orchestrator import Orchestrator
from efferents.agents.state import init_lab, lab_paths, load_state, recent_runs, runs_count
from efferents.migrations.runner import apply_campaigns_migration


def _load_dotenv(path: str | Path = ".env") -> None:
    """Tiny .env loader (no python-dotenv dependency). KEY=VALUE per line.

    .env values OVERRIDE existing env vars — per-project keys win over shell-wide
    settings. This is intentional: the project's .env should be the source of
    truth for the agent loop's spend.
    """
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _make_client_or_die() -> anthropic.Anthropic:
    _load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set (checked env and .env).", file=sys.stderr)
        sys.exit(2)
    return anthropic.Anthropic()


def cmd_start(args: argparse.Namespace) -> int:
    _load_dotenv()
    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set (checked env and .env).", file=sys.stderr)
        return 2
    o = Orchestrator(
        lab_dir=args.lab,
        context_dir=args.context,
        daily_cap_usd=args.daily_cap,
        runs_per_digest=args.runs_per_digest,
        hours_per_digest=args.hours_per_digest,
        runs_per_coder=args.runs_per_coder,
        hours_per_coder=args.hours_per_coder,
        dry_run=args.dry_run,
        startup_message=f"daily_cap=${args.daily_cap:.0f}, dry_run={args.dry_run}",
    )
    o.run(max_iterations=args.max if args.max > 0 else None)
    # Exit code 42 signals "Coder committed new code; please re-spawn me".
    # The wrapper script (ops/start.sh) loops on this case to reload modules.
    if o.restart_requested:
        return 42
    return 0


def cmd_code_once(args: argparse.Namespace) -> int:
    """Pick the top pending architectural proposal and try to implement it once."""
    paths = lab_paths(args.lab)
    init_lab(paths)
    apply_campaigns_migration(paths.runs_db)
    budget = BudgetTracker(paths.budget, daily_cap_usd=args.daily_cap)
    client = _make_client_or_die()
    proposal = coder.select_pending_proposal(paths=paths)
    if proposal is None:
        print(json.dumps({"ok": False, "reason": "no pending proposals"}))
        return 1
    print(f"Implementing: {proposal['name']}", file=sys.stderr)
    result = coder.implement_proposal(
        proposal=proposal,
        paths=paths,
        budget=budget,
        client=client,
    )
    print(json.dumps({
        "ok": result.ok,
        "feasible": result.feasible,
        "name": result.name,
        "summary": result.summary,
        "files_changed": result.files_changed,
        "commit_sha": result.commit_sha,
        "error": result.error,
    }, indent=2))
    return 0 if result.ok else 1


def cmd_propose_once(args: argparse.Namespace) -> int:
    paths = lab_paths(args.lab)
    init_lab(paths)
    apply_campaigns_migration(paths.runs_db)
    budget = BudgetTracker(paths.budget, daily_cap_usd=args.daily_cap)
    client = _make_client_or_die()
    out = researcher.propose(
        paths=paths, context_dir=Path(args.context), budget=budget, client=client
    )
    print(json.dumps(out, indent=2))
    return 0


def cmd_digest_now(args: argparse.Namespace) -> int:
    paths = lab_paths(args.lab)
    init_lab(paths)
    apply_campaigns_migration(paths.runs_db)
    budget = BudgetTracker(paths.budget, daily_cap_usd=args.daily_cap)
    client = _make_client_or_die()
    out = analyst.write_digest(
        paths=paths,
        context_dir=Path(args.context),
        budget=budget,
        client=client,
        notify=not args.no_notify,
    )
    print(json.dumps(out, indent=2))
    return 0


def cmd_progress_now(args: argparse.Namespace) -> int:
    """Regenerate lab/progress.html on demand. No API calls, no budget."""
    from efferents.agents.progress import write_progress

    paths = lab_paths(args.lab)
    init_lab(paths)
    apply_campaigns_migration(paths.runs_db)
    out_path = write_progress(paths, context_dir=args.context)
    print(json.dumps({"path": str(out_path)}, indent=2))
    return 0


def cmd_write_once(args: argparse.Namespace) -> int:
    _load_dotenv()
    out = writer.write_once(
        lab=args.lab,
        paper=args.paper,
        reports=args.reports,
        context=args.context,
        skip_llm=args.skip_llm,
        skip_notify=args.no_notify,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_start_writer(args: argparse.Namespace) -> int:
    _load_dotenv()
    if not args.skip_llm and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set (checked env and .env).", file=sys.stderr)
        return 2
    writer.run_loop(
        lab=args.lab,
        paper=args.paper,
        reports=args.reports,
        context=args.context,
        runs_per_write=args.runs_per_write,
        hours_per_write=args.hours_per_write,
        check_every_seconds=args.check_every,
        skip_llm=args.skip_llm,
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    paths = lab_paths(args.lab)
    init_lab(paths)
    apply_campaigns_migration(paths.runs_db)
    budget = BudgetTracker(paths.budget)
    state = load_state(paths.state)
    nrows = runs_count(paths.runs_db)
    print(f"runs total : {nrows}")
    print(f"queue size : {paths.queue.stat().st_size if paths.queue.exists() else 0} bytes")
    print(f"budget today: ${budget.spend_today():.4f}")
    print(f"budget total: ${budget.spend_total():.4f}")
    cs = budget.cache_stats(50)
    print(
        f"cache       : reads {cs['cache_read_share']*100:.0f}% / "
        f"creates {cs['cache_create_share']*100:.0f}% / "
        f"fresh {cs['fresh_input_share']*100:.0f}% (last {cs['n_calls']} calls)"
    )
    print(f"last digest : {state.get('last_digest_path', '(none)')}")
    print()
    rows = recent_runs(paths.runs_db, n=10)
    if rows:
        print("recent runs:")
        for r in rows:
            print(
                f"  {r['started_at'][:19]}  {r['model']:>3}  "
                f"raw_q={r['raw_q']}  E_w1={r['e_w1']:.3g}  "
                f"radL2log={r['radial_l2_log']:.3g}  ({r['eval_kind']})"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agents")
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--lab", default="lab")
    common.add_argument("--context", default="context")
    common.add_argument("--daily-cap", type=float, default=100.0)

    p_start = sub.add_parser("start", parents=[common], help="run the loop")
    p_start.add_argument("--dry-run", action="store_true")
    p_start.add_argument("--max", type=int, default=0, help="max iterations (0 = forever)")
    p_start.add_argument("--runs-per-digest", type=int, default=40)
    p_start.add_argument("--hours-per-digest", type=float, default=4.0)
    p_start.add_argument("--runs-per-coder", type=int, default=8,
                         help="fire Coder after N runs since last attempt")
    p_start.add_argument("--hours-per-coder", type=float, default=6.0,
                         help="fire Coder after H hours since last attempt")
    p_start.set_defaults(func=cmd_start)

    p_code = sub.add_parser("code-once", parents=[common], help="one Coder attempt")
    p_code.set_defaults(func=cmd_code_once)

    p_prop = sub.add_parser("propose-once", parents=[common], help="one Researcher call")
    p_prop.set_defaults(func=cmd_propose_once)

    p_prog = sub.add_parser("progress-now", parents=[common], help="regenerate lab/progress.html (no API calls)")
    p_prog.set_defaults(func=cmd_progress_now)

    p_dig = sub.add_parser("digest-now", parents=[common], help="force a digest")
    p_dig.add_argument("--no-notify", action="store_true")
    p_dig.set_defaults(func=cmd_digest_now)

    p_write = sub.add_parser("write-once", parents=[common], help="one Writer pass")
    p_write.add_argument("--paper", default="paper", help="paper/ directory (writer's outputs)")
    p_write.add_argument("--reports", default="reports", help="reports/ directory")
    p_write.add_argument("--skip-llm", action="store_true", help="run only the deterministic phase")
    p_write.add_argument("--no-notify", action="store_true")
    p_write.set_defaults(func=cmd_write_once)

    p_loop = sub.add_parser("start-writer", parents=[common], help="continuous Writer loop")
    p_loop.add_argument("--paper", default="paper")
    p_loop.add_argument("--reports", default="reports")
    p_loop.add_argument("--runs-per-write", type=int, default=15,
                        help="fire after N new runs accumulated since last pass")
    p_loop.add_argument("--hours-per-write", type=float, default=5.0,
                        help="fire after H hours, regardless of run count (if any new runs)")
    p_loop.add_argument("--check-every", type=int, default=60,
                        help="poll interval in seconds")
    p_loop.add_argument("--skip-llm", action="store_true")
    p_loop.set_defaults(func=cmd_start_writer)

    p_stat = sub.add_parser("status", parents=[common], help="print state")
    p_stat.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
