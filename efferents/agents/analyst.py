"""Analyst agent: periodic digest writer. Reads recent runs + notebook + context,
writes a markdown digest. Notifies the user via macOS + ntfy.sh.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from efferents import lab as _lab
from efferents.agents.budget import BudgetTracker, CallUsage, model_for
from efferents.agents.notify import notify_all
from efferents.agents.prompts.loader import load_prompt
from efferents.agents.state import LabPaths, load_state, notebook_append, notebook_tail, now_iso, read_context, recent_runs, save_state


def _flat_digest_epsilon() -> float:
    return _lab.get_config().metrics.flat_digest_epsilon


def group_runs_by_campaign(runs: list[dict]) -> dict[str | None, list[dict]]:
    out: dict[str | None, list[dict]] = {}
    for r in runs:
        key = r.get("campaign_id")
        out.setdefault(key, []).append(r)
    return out


def _load_campaign(db_path: Path, campaign_id: str) -> dict | None:
    """Load a single campaign row from runs.sqlite. Returns None if not found."""
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        try:
            row = conn.execute(
                "SELECT id, question, hypothesis_hash FROM campaigns WHERE id = ?",
                (campaign_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
    finally:
        conn.close()
    return dict(row) if row else None


def _format_campaign_blocks(groups: dict[str | None, list[dict]], db_path: Path) -> str:
    """Format grouped runs as a markdown narrative of campaign blocks."""
    metric_keys = ["e_w1", "val_x0_mse", "radial_l2_log", "active_frac_w1"]
    lines: list[str] = []

    for campaign_id, runs in groups.items():
        if campaign_id is None:
            continue
        campaign = _load_campaign(db_path, campaign_id)
        question = campaign["question"] if campaign else "(unknown question)"
        h_hash = campaign["hypothesis_hash"] if campaign else ""
        lines.append(f"### Campaign {campaign_id} — {question}")
        if h_hash:
            lines.append(f"Hypothesis hash: {h_hash}")
        lines.append("Runs in this campaign:")
        for r in runs:
            parts = [f"- {r.get('run_id', '?')}:"]
            for k in metric_keys:
                v = r.get(k)
                if v is not None:
                    parts.append(f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}")
            lines.append(" ".join(parts))
        lines.append("")

    # Uncampaigned runs
    if None in groups:
        lines.append("### Uncampaigned runs")
        for r in groups[None]:
            parts = [f"- {r.get('run_id', '?')}:"]
            for k in metric_keys:
                v = r.get(k)
                if v is not None:
                    parts.append(f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}")
            lines.append(" ".join(parts))
        lines.append("")

    return "\n".join(lines).strip()


def _format_recent_runs(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no runs yet)"
    cols = [
        "run_id", "started_at", "model", "seed", "raw_q", "epochs", "aug_depth",
        "aug_shared_unitary", "cond_drop_p", "eval_kind",
        "val_x0_mse", "e_w1", "radial_l2_log", "active_frac_w1",
        "duration_seconds", "config_hash",
    ]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        cells = [
            f"{r[c]:.4g}" if isinstance(r.get(c), float) else ("" if r.get(c) is None else str(r[c]))
            for c in cols
        ]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _budget_snapshot(budget: BudgetTracker) -> str:
    today = budget.spend_today()
    total = budget.spend_total()
    cap = budget.daily_cap
    cache = budget.cache_stats(50)
    hit = cache["cache_read_share"] * 100
    return (
        f"Today: ${today:.2f} of ${cap:.2f} cap. "
        f"Total: ${total:.2f}. "
        f"Cache read share (last 50 calls): {hit:.0f}%."
    )


def _build_messages(
    *,
    vision: str,
    decisions: str,
    research_log: str,
    recent_runs_table: str,
    notebook: str,
    budget_snapshot: str,
    campaign_blocks: str = "",
) -> list[dict[str, Any]]:
    static_block = "## Vision\n\n" + vision + "\n\n## Decisions\n\n" + decisions
    campaign_section = ("\n\n## Runs grouped by campaign\n\n" + campaign_blocks) if campaign_blocks else ""
    dynamic_block = (
        "## Research log\n\n" + research_log
        + campaign_section
        + "\n\n## Recent runs\n\n" + recent_runs_table
        + "\n\n## Lab notebook tail\n\n" + notebook
        + "\n\n## Budget snapshot\n\n" + budget_snapshot
    )
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic_block, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": "Write the digest now per your system-prompt format."},
            ],
        }
    ]


def write_digest(
    *,
    paths: LabPaths,
    context_dir: str | Path,
    budget: BudgetTracker,
    client: anthropic.Anthropic,
    model: str | None = None,
    max_tokens: int = 2048,
    n_recent: int = 50,
    notify: bool = True,
) -> dict[str, Any]:
    ctx = read_context(context_dir)
    rows = recent_runs(paths.runs_db, n=n_recent)
    system_prompt = load_prompt("analyst")

    groups = group_runs_by_campaign(rows)
    campaign_blocks = _format_campaign_blocks(groups, paths.runs_db)

    messages = _build_messages(
        vision=ctx.get("vision.md", ""),
        decisions=ctx.get("decisions.md", ""),
        research_log=ctx.get("research_log.md", ""),
        recent_runs_table=_format_recent_runs(rows),
        notebook=notebook_tail(paths.notebook, max_chars=8000),
        budget_snapshot=_budget_snapshot(budget),
        campaign_blocks=campaign_blocks,
    )

    chosen = model or model_for("analyst")
    if chosen is None:
        raise RuntimeError("No model configured for Analyst")

    resp = client.messages.create(
        model=chosen,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )

    usage = CallUsage(
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        cache_creation_input_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
    )
    budget.record(agent="analyst", model=chosen, usage=usage)

    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    digest_path = paths.digests_dir / f"{ts}.md"
    digest_path.write_text(text)

    notebook_append(paths.notebook, f"## {ts} — digest\n\nWrote `{digest_path}`.\n")

    notified = {}
    if notify:
        # Push the TL;DR (first ~300 chars after the heading) to the phone.
        tl = _extract_tldr(text)
        notified = notify_all(
            title=f"{_lab.get_config().lab_id} digest",
            message=f"{tl}\n\nFull: {digest_path}",
        )

    ws = [r["e_w1"] for r in rows if r.get("e_w1") is not None]
    best_w1 = min(ws) if ws else None
    state = load_state(paths.state)
    state = update_flat_digest_counter(state, current_best_w1=best_w1, epsilon=0.005)
    save_state(paths.state, state)

    # Best-effort progress dashboard refresh. Never let a rendering bug kill a digest.
    try:
        from efferents.agents.progress import write_progress
        write_progress(paths, context_dir=context_dir)
    except Exception as exc:
        notebook_append(
            paths.notebook,
            f"## {now_iso()} — progress.html refresh FAILED: {type(exc).__name__}: {exc}\n",
        )

    return {"path": str(digest_path), "tokens": (usage.input_tokens, usage.output_tokens), "notify": notified}


def update_flat_digest_counter(
    state: dict, *, current_best_w1: float | None, epsilon: float | None = None
) -> dict:
    """Return a new state dict with `digests_without_improvement` and
    `last_digest_best_w1` updated based on this digest's current best W1.

    epsilon: absolute improvement threshold; a drop in W1 by more than
    epsilon counts as improvement (resets counter). Defaults to
    ``_flat_digest_epsilon()`` (reads from the active LabConfig) when not
    supplied explicitly.
    """
    if epsilon is None:
        epsilon = _flat_digest_epsilon()
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


def _extract_tldr(digest: str) -> str:
    lines = digest.splitlines()
    out = []
    in_tldr = False
    for line in lines:
        if line.strip().lower().startswith("## tl;dr"):
            in_tldr = True
            continue
        if in_tldr and line.strip().startswith("## "):
            break
        if in_tldr:
            out.append(line)
    text = "\n".join(out).strip()
    return text[:300] if text else digest[:300]
