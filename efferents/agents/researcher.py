"""Researcher agent — Student↔Supervisor dialogue producing config + architectural proposals.

The orchestrator's call boundary is unchanged: ``propose()`` returns
``{proposals, architectural_proposals, consulted_topic_ids, raw}`` and persists
architectural proposals to ``lab/proposed_changes.md`` exactly as before. The
dialogue is a private implementation detail.

Internal flow (each iteration):

    Turn 0  _saturation_report(paths)                              # deterministic
    Turn 1  Supervisor brief    (Sonnet by default; Opus when streak ≥ 2)
    Turn 2  Student propose     (Sonnet, with lit_review tool)
    Turn 3  Supervisor review   (same model as the brief)

A single ``$1.00`` per-call cost guardrail aborts the review turn (Student
output is returned verbatim). A circuit-breaker bypasses the Supervisor
entirely after two consecutive empty-proposal iterations — falling back to a
single Student-only call so the queue never starves.

State (in ``lab/state.json``):
    supervisor_opus_streak      : int  iterations of consecutive saturation ≥ 1
    researcher_consecutive_empty: int  consecutive empty propose() returns

Observability:
    Each call appends one row to ``lab/researcher_dialogue.jsonl`` (no reader).

Output schema for the Coder is unchanged.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import anthropic

from efferents.agents import librarian
from efferents.agents import popper_gate as _popper_gate
from efferents.agents.budget import (
    BudgetTracker,
    CallUsage,
    SUPERVISOR_OPUS_STREAK_THRESHOLD,
    model_for,
    model_for_supervisor,
)
from efferents.agents.state import (
    LabPaths,
    StudentStateView,
    append_jsonl,
    campaign_insert as _campaign_insert,
    campaign_open_list as _campaign_open_list,
    campaign_open_list_for_student as _campaign_open_list_for_student,
    campaign_recently_closed_list as _campaign_recently_closed_list,
    load_state,
    notebook_append,
    notebook_tail,
    now_iso,
    parse_json_loose,
    parse_json_with_one_retry,
    read_context,
    read_jsonl,
    recent_runs,
    retry_hint,
    save_state,
)
from efferents import lab as _lab

PROMPTS_DIR = Path(__file__).parent / "prompts"
STUDENT_PROMPT_PATH = PROMPTS_DIR / "student.md"
SUPERVISOR_PROMPT_PATH = PROMPTS_DIR / "supervisor.md"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")

MAX_LIT_CALLS_PER_PASS = 5
PER_CALL_COST_CAP_USD = 1.00
EMPTY_FALLBACK_THRESHOLD = 2  # consecutive empty propose() returns → bypass Supervisor


# -----------------------------------------------------------------------------
# Deterministic helpers
# -----------------------------------------------------------------------------


def _format_recent_runs(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no runs yet)"
    cols = [
        "run_id", "model", "seed", "raw_q", "epochs", "aug_depth",
        "aug_shared_unitary", "cond_drop_p", "eval_kind",
        "val_x0_mse", "e_w1", "radial_l2_log", "duration_seconds", "config_hash",
    ]
    out = ["| " + " | ".join(cols) + " |"]
    out.append("|" + "|".join("---" for _ in cols) + "|")
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c)
            if isinstance(v, float):
                cells.append(f"{v:.4g}")
            else:
                cells.append("" if v is None else str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _read_default_config() -> str:
    p = Path("config/default.yaml")
    return p.read_text() if p.exists() else "(missing)"


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# Primary metrics in priority order. Each measures distance from generated
# samples to REAL jet data (lower is better; 0 is perfect):
#   e_w1            — energy-Wasserstein-1 on per-jet total intensity.
#   radial_l2_log   — log-RMS of the radial energy-density profile mismatch.
#                     Sensitive to halo/tail spread — "samples look smeared".
#   active_frac_w1  — Wasserstein-1 on the fraction of pixels above the
#                     99.5th-percentile threshold. Captures sparsity / how
#                     concentrated the support is, also a visual metric.
PRIMARY_METRICS = ("e_w1", "radial_l2_log", "active_frac_w1")


def _saturation_report(paths: LabPaths, *, n: int = 50) -> dict[str, Any]:
    """Detect saturated experimental axes across all primary metrics.

    Within each (model, raw_q, eval_kind) bucket, computes the saturation
    heuristic independently per metric in ``PRIMARY_METRICS``:

    - per-seed noise floor: mean of within-config stds where ≥2 runs share
      a config_hash;
    - cross-config delta: std of best-per-config metric values;
    - top-quartile floor: std/mean of the best 25% of bests (catches the
      case where the best results are clustered after many attempts).

    A metric is saturated for that bucket when:

    - same-config replication exists AND cross_std ≤ 1.5 × seed_noise; or
    - no replication AND n_configs ≥ 10 (many tries, no breakthrough); or
    - no replication AND n_configs ≥ 6 AND top-quartile floor_ratio < 0.10.

    A bucket as a whole is saturated when **≥ 2 of 3 primary metrics** are
    saturated — single-metric saturation can be a coincidence, but if energy
    AND radial profile (or AND sparsity) both stall, the axis is truly stuck.
    """
    if not paths.runs_db.exists():
        return {"saturated_axes": [], "score": 0, "evidence": []}

    conn = sqlite3.connect(paths.runs_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT model, raw_q, eval_kind, config_hash, "
            "       e_w1, radial_l2_log, active_frac_w1 "
            "FROM runs WHERE e_w1 IS NOT NULL "
            "ORDER BY started_at DESC LIMIT ?",
            (n,),
        ).fetchall()
    finally:
        conn.close()

    # Bucket: (model, raw_q, eval_kind) -> {config_hash: {metric: [vals]}}
    buckets: dict[tuple[str, int, str], dict[str, dict[str, list[float]]]] = (
        defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    )
    for r in rows:
        key = (str(r["model"]), int(r["raw_q"] or 0), str(r["eval_kind"] or "unknown"))
        ch = str(r["config_hash"])
        for m in PRIMARY_METRICS:
            v = r[m]
            if v is not None:
                buckets[key][ch][m].append(float(v))

    def _metric_status(per_hash: dict[str, dict[str, list[float]]], metric: str) -> dict[str, Any]:
        vals_per_config = [d[metric] for d in per_hash.values() if d.get(metric)]
        if len(vals_per_config) < 4:
            return {"n_configs": len(vals_per_config), "saturated": False, "rule": "n<4"}
        bests = [min(vs) for vs in vals_per_config]
        cross_std = _stdev(bests)
        within_stds = [_stdev(vs) for vs in vals_per_config if len(vs) >= 2]
        seed_noise = sum(within_stds) / len(within_stds) if within_stds else None
        sorted_bests = sorted(bests)
        top_q = sorted_bests[: max(2, len(sorted_bests) // 4)]
        floor_mean = sum(top_q) / len(top_q)
        floor_ratio = (_stdev(top_q) / floor_mean) if floor_mean > 0 else 0.0
        n_configs = len(vals_per_config)
        if seed_noise is not None and seed_noise > 0:
            if cross_std <= 1.5 * seed_noise:
                return {
                    "n_configs": n_configs, "saturated": True, "best": min(bests),
                    "rule": f"cross_std={cross_std:.3g} ≤ 1.5×seed_noise={seed_noise:.3g}",
                }
        if n_configs >= 10:
            return {
                "n_configs": n_configs, "saturated": True, "best": min(bests),
                "rule": f"n_configs={n_configs} ≥ 10 (no breakthrough)",
            }
        if n_configs >= 6 and floor_ratio < 0.10:
            return {
                "n_configs": n_configs, "saturated": True, "best": min(bests),
                "rule": f"n_configs={n_configs}, floor_ratio={floor_ratio:.3f} < 0.10",
            }
        return {"n_configs": n_configs, "saturated": False, "best": min(bests), "rule": ""}

    saturated_axes: list[str] = []
    evidence: list[dict[str, Any]] = []
    for (model, raw_q, eval_kind), per_hash in buckets.items():
        per_metric = {m: _metric_status(per_hash, m) for m in PRIMARY_METRICS}
        n_sat = sum(1 for s in per_metric.values() if s["saturated"])
        is_saturated = n_sat >= 2  # ≥ 2 of 3 primary metrics stuck
        # Total runs in this bucket (any metric).
        all_vals = sum(
            (per_hash[ch].get("e_w1", []) for ch in per_hash), []
        )
        n_configs = len([ch for ch in per_hash if per_hash[ch].get("e_w1")])

        ev = {
            "bucket": f"model={model} raw_q={raw_q} eval_kind={eval_kind}",
            "n_configs": n_configs,
            "n_runs": sum(
                len(per_hash[ch].get("e_w1", [])) for ch in per_hash
            ),
            "per_metric": {
                m: {
                    "best": round(s["best"], 4) if s.get("best") is not None else None,
                    "saturated": s["saturated"],
                    "rule": s["rule"],
                }
                for m, s in per_metric.items()
            },
            "n_saturated_metrics": n_sat,
            "saturated": is_saturated,
        }
        evidence.append(ev)
        if is_saturated:
            # Name the saturated metrics in the axis label so the Supervisor's
            # brief can be specific about what's stuck.
            stuck = [m for m, s in per_metric.items() if s["saturated"]]
            saturated_axes.append(
                f"model={model} raw_q={raw_q} eval_kind={eval_kind} "
                f"on metrics {stuck}"
            )

    score = min(len(saturated_axes), 5)
    return {"saturated_axes": saturated_axes, "score": score, "evidence": evidence}


def _ensure_lit_context(
    proposals: list[dict[str, Any]], consulted: list[str]
) -> list[dict[str, Any]]:
    """Backfill ``lit_context`` on proposals that omitted it."""
    for p in proposals:
        if "lit_context" not in p or not isinstance(p["lit_context"], list):
            p["lit_context"] = list(consulted)
    return proposals


def _persist_architectural(path: Path, items: list[dict[str, Any]]) -> None:
    """Append architectural proposals to a markdown log for the Coder."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [f"\n## {ts}\n"]
    for it in items:
        lines.append(f"### {it.get('name', '(unnamed)')}\n")
        if it.get("principle"):
            lines.append(f"- **Principle**: {it['principle']}")
        if it.get("what"):
            lines.append(f"- **What**: {it['what']}")
        if it.get("why"):
            lines.append(f"- **Why**: {it['why']}")
        if it.get("expected_effort"):
            lines.append(f"- **Effort**: {it['expected_effort']}")
        if it.get("expected_payoff"):
            lines.append(f"- **Payoff**: {it['expected_payoff']}")
        if it.get("requires_new_file"):
            lines.append(f"- **NewFiles**: {', '.join(it.get('new_files') or []) or '(unspecified)'}")
        lines.append("")
    text = "\n".join(lines) + "\n"
    if not path.exists():
        path.write_text(
            "# Proposed architectural changes\n\n"
            "Researcher-authored ideas that require code changes (not config-only). "
            "Coder agent reads from here.\n"
        )
    with path.open("a") as f:
        f.write(text)


# -----------------------------------------------------------------------------
# Anthropic call helpers
# -----------------------------------------------------------------------------


def _simple_call(
    *,
    client: anthropic.Anthropic,
    system: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    model: str,
    agent: str,
    budget: BudgetTracker,
    max_tokens: int,
    notes: str = "",
) -> str:
    """One-shot ``messages.create`` without tools. Records spend, returns text."""
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    usage = CallUsage(
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        cache_creation_input_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
    )
    budget.record(
        agent=agent, model=model, usage=usage,
        notes=f"{notes} | stop={resp.stop_reason}".strip(" |"),
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


# -----------------------------------------------------------------------------
# Context blocks shared by Student + Supervisor
# -----------------------------------------------------------------------------


def _shared_static_block(*, vision: str, decisions: str) -> str:
    return (
        "## Vision\n\n" + vision
        + "\n\n## Decisions\n\n" + decisions
        + "\n\n## Default config (config/default.yaml)\n\n"
        + "Use ONLY keys that appear in this YAML when emitting `config_overrides`. "
        + "Dotted paths must match this structure exactly (e.g., `eval.centering`, "
        + "not `data.centering`).\n\n```yaml\n"
        + _read_default_config()
        + "\n```"
    )


def _shared_dynamic_block(*, research_log: str, runs_table: str, notebook: str) -> str:
    return (
        "## Research log (human-curated)\n\n" + research_log
        + "\n\n## Recent runs\n\n" + runs_table
        + "\n\n## Lab notebook tail\n\n" + notebook
    )


def _kb_block(kb_index: str) -> str:
    return (
        "## kb cache index\n\n"
        "These topic_ids are already in lab/knowledge/kb.sqlite — calling "
        "`lit_review` with the same topic+intent returns the cached row "
        "instantly (no web search). Reuse these instead of re-querying.\n\n"
        + kb_index
    )


def _coder_log_tail(paths: LabPaths, n: int = 10) -> str:
    log = read_jsonl(paths.root / "coder_log.jsonl")[-n:]
    if not log:
        return "(no Coder attempts yet)"
    out = []
    for r in log:
        ok = "✓" if r.get("ok") else ("infeasible" if not r.get("feasible") else "✗")
        out.append(
            f"- {ok} {r.get('name','?')} | files={r.get('files_changed') or []} "
            f"| commit={r.get('commit_sha') or '-'} | err={r.get('error') or ''}"
        )
    return "\n".join(out)


# -----------------------------------------------------------------------------
# Dialogue turns
# -----------------------------------------------------------------------------


def _supervisor_brief(
    *,
    client: anthropic.Anthropic,
    paths: LabPaths,
    budget: BudgetTracker,
    sup_model: str,
    static_block: str,
    kb_index_block: str,
    dynamic_block: str,
    saturation: dict[str, Any],
    coder_log: str,
    mode: str = "refine",
    student_id: str = "primary",
) -> dict[str, Any]:
    """Turn 1: Supervisor reads state and produces an agenda JSON."""
    system_text = SUPERVISOR_PROMPT_PATH.read_text()
    system = [{
        "type": "text", "text": system_text,
        "cache_control": {"type": "ephemeral"},
    }]

    from efferents.agents import coder as _coder_mod
    blockers = _coder_mod.recent_blockers(paths, student_id=student_id)
    blockers_block = (
        "\n\n## Coder blockers (do NOT re-propose these architectural names)\n\n"
        + (
            "\n".join(f"- `{b['name']}` ({b['date']}): {b['reason']}" for b in blockers)
            if blockers else "(none in the last 30 days)"
        )
    )

    try:
        recently_closed = _campaign_recently_closed_list(paths.runs_db, _lab.LAB_ID, days=7)
    except sqlite3.OperationalError:
        # campaigns table absent (pre-migration DB); skip the block.
        recently_closed = []
    closed_block = (
        "\n\n## Recently closed campaigns (last 7 days)\n\n"
        "Do NOT propose for these `campaign_id`s — they are resolved.\n\n"
        + (
            "\n".join(
                f"- `{c['id']}` (closed {c.get('closed_at','')[:19]}) — "
                f"reason: {c.get('close_reason') or '?'} — "
                f"question: {c.get('question','')[:100]}"
                for c in recently_closed
            )
            if recently_closed else "(none in the last 7 days)"
        )
    )

    # Recent findings from sibling autolabs, pulled by federation.consume.
    # See agents/federation.py. The Student should treat these as background
    # context AND as candidates to cite via `lit_context`. When the Student's
    # hypothesis would be FALSE if an external claim is wrong, it must mark
    # that claim as foundational (foundational_external field on the
    # proposal), so the lab can reproduce it before building on it.
    from efferents.agents import federation as _federation
    paper_dir = paths.root.parent / "paper"
    external_recent = _federation.recent_external_entries(
        paper_dir / "external_journal.md",
        days=14, max_n=10,
    )
    external_block = (
        "\n\n## Recent findings from sibling autolabs (last 14 days)\n\n"
        + (
            "\n".join(
                f"- `{e.get('lab_id','?')}/{e['campaign_id']}` — "
                f"{e.get('headline','(no headline)')[:120]}"
                for e in external_recent
            )
            if external_recent
            else "(none — `python -m agents.federation consume --from <path>` pulls a sibling journal)"
        )
    )

    # External claims we've cited as FOUNDATIONAL but haven't yet reproduced.
    # Discipline: a paper our hypothesis depends on must be reproduced before
    # we build on it. Reproductions live in paper/reproductions.md; per-
    # proposal dependencies live in lab/foundational_deps.jsonl.
    pending_deps = _federation.pending_foundational_deps(
        paths.root / "foundational_deps.jsonl",
        paper_dir,
        max_age_days=30,
    )
    foundational_block = (
        "\n\n## Foundational external claims pending reproduction\n\n"
        "When we cite a sibling lab's finding as a *premise* of our work, we "
        "must reproduce it BEFORE building further. Pending verifications:\n\n"
        + (
            "\n".join(
                f"- `{d['lab_id']}/{d['campaign_id']}` (status: {d['status'] or 'never attempted'}) — "
                f"cited because: {d['why'][:80]}"
                for d in pending_deps
            )
            if pending_deps else "(no unverified foundational deps — good)"
        )
    )

    extra = (
        f"<<MODE: {mode}>>\n\n"
        + "## Saturation report (deterministic)\n\n"
        + json.dumps(saturation, indent=2)
        + "\n\n## Recent Coder attempts\n\n" + coder_log
        + blockers_block
        + closed_block
        + external_block
        + foundational_block
        + "\n\n---\n\n"
        + "Emit your **brief-turn JSON** now. First character `{`. "
        "Address the saturation report. Add infeasible names to "
        "`forbidden_axes`. Do not target closed campaigns. If foundational "
        "deps are pending, surface that — the Student should propose a "
        "reproduction run before piling on further claims. ≤400 output tokens."
    )

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": kb_index_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": dynamic_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": extra},
        ],
    }]

    def _call(retry_msgs):
        final_msgs = messages + (retry_msgs or [])
        return _simple_call(
            client=client, system=system, messages=final_msgs,
            model=sup_model, agent="supervisor", budget=budget,
            max_tokens=2048, notes="brief" + (" (retry)" if retry_msgs else ""),
        )

    parsed, _status = parse_json_with_one_retry(
        call_fn=_call,
        must_contain='"expected_proposal_shape"',
        fallback={
            "open_questions": [],
            "forbidden_axes": [],
            "encouraged_paradigms": [],
            "expected_proposal_shape": "architectural",
            "post_mortem": "[supervisor brief failed to parse after one retry]",
            "_parse_error": True,
        },
    )
    return parsed


def _student_propose(
    *,
    client: anthropic.Anthropic,
    paths: LabPaths,
    budget: BudgetTracker,
    student_model: str,
    static_block: str,
    kb_index_block: str,
    dynamic_block: str,
    brief: dict[str, Any],
    max_tokens: int,
    mode: str = "refine",
    student_id: str = "primary",
) -> tuple[str, dict[str, Any], list[str]]:
    """Turn 2: Student takes the brief and produces proposals.

    `student_id` selects which prompt template to use (per
    auto_qml.lab.STUDENTS[student_id]["prompt_overrides"]["student"], if
    present; otherwise the default agents/prompts/student.md).

    Returns (raw_text, parsed_dict_or_empty, consulted_topic_ids).
    """
    # Look up a per-student prompt override; fall back to the default.
    prompt_path = STUDENT_PROMPT_PATH
    try:
        student = _lab.get_student(student_id)
    except KeyError:
        student = None
    if student:
        override = (student.get("prompt_overrides") or {}).get("student")
        if override:
            candidate = Path(override) if Path(override).is_absolute() else Path(__file__).parent.parent / override
            if candidate.exists():
                prompt_path = candidate
    system_text = prompt_path.read_text()
    # If the student dict has a `focus`, prepend it so this student's prompt
    # carries its area-of-interest cleanly without needing a full prompt clone.
    if student and student.get("focus") and prompt_path == STUDENT_PROMPT_PATH:
        system_text = (
            f"## Your focus (student: {student_id})\n\n{student['focus']}\n\n"
            "Stay within this focus when picking proposals; tell the Supervisor "
            "explicitly when a finding from outside the focus should change the "
            "direction.\n\n---\n\n"
        ) + system_text
    system = [{
        "type": "text", "text": system_text,
        "cache_control": {"type": "ephemeral"},
    }]

    brief_block = (
        "## Supervisor brief (binding for this turn)\n\n```json\n"
        + json.dumps(brief, indent=2)
        + "\n```"
    )

    # Anthropic caps cache_control at 4 blocks. System prompt (1) + 3 cached
    # user blocks fills the budget; the brief and trailing instruction stay
    # uncached (the brief changes every iteration anyway).
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": kb_index_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": dynamic_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": brief_block},
            {
                "type": "text",
                "text": (
                    f"<<MODE: {mode}>>\n\n"
                    "Produce 1–3 proposals consistent with the Supervisor brief. "
                    "Call `lit_review` first if entering a new conceptual area. "
                    "Output strict JSON. First character `{`."
                ),
            },
        ],
    }]

    text, consulted = librarian.run_with_lit_review_tool(
        client=client,
        system_prompt=system,
        messages=messages,
        model=student_model,
        paths=paths,
        budget=budget,
        agent="student",
        max_tokens=max_tokens,
        max_lit_calls=MAX_LIT_CALLS_PER_PASS,
    )
    # `run_with_lit_review_tool` mutated `messages` to hold the full tool-use
    # round-trip history (but NOT the final assistant text). On parse failure,
    # we append that final text + a retry hint and ask once more without
    # re-enabling the tool — the second call is purely a "fix the JSON" pass.
    try:
        parsed = parse_json_loose(text, must_contain='"proposals"')
        return text, parsed, consulted
    except json.JSONDecodeError as e:
        retry_msgs = [
            {"role": "assistant", "content": [{"type": "text", "text": text}]},
            {"role": "user", "content": [
                {"type": "text", "text": retry_hint(str(e), '"proposals"')}
            ]},
        ]
        text2 = _simple_call(
            client=client, system=system, messages=messages + retry_msgs,
            model=student_model, agent="student", budget=budget,
            max_tokens=max_tokens, notes="propose (retry)",
        )
        try:
            parsed = parse_json_loose(text2, must_contain='"proposals"')
            return text2, parsed, consulted
        except json.JSONDecodeError:
            parsed = {"proposals": [], "architectural_proposals": [], "_parse_error": True}
            return text2, parsed, consulted


def _supervisor_review(
    *,
    client: anthropic.Anthropic,
    paths: LabPaths,
    budget: BudgetTracker,
    sup_model: str,
    static_block: str,
    student_parsed: dict[str, Any],
    saturation: dict[str, Any],
) -> dict[str, Any]:
    """Turn 3: Supervisor critiques the Student output."""
    system_text = SUPERVISOR_PROMPT_PATH.read_text()
    system = [{
        "type": "text", "text": system_text,
        "cache_control": {"type": "ephemeral"},
    }]

    review_input = (
        "## Saturation report (reminder)\n\n"
        + json.dumps(saturation, indent=2)
        + "\n\n## Student output\n\n```json\n"
        + json.dumps(
            {
                "proposals": student_parsed.get("proposals", []),
                "architectural_proposals": student_parsed.get("architectural_proposals", []),
            },
            indent=2,
        )
        + "\n```\n\n---\n\n"
        + "Emit your **review-turn JSON** now. First character `{`. "
        "≤300 output tokens. Default to `approve` unless the Student violated "
        "a hard rule from the brief."
    )

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": review_input},
        ],
    }]

    def _call(retry_msgs):
        final_msgs = messages + (retry_msgs or [])
        return _simple_call(
            client=client, system=system, messages=final_msgs,
            model=sup_model, agent="supervisor", budget=budget,
            max_tokens=800, notes="review" + (" (retry)" if retry_msgs else ""),
        )

    parsed, _status = parse_json_with_one_retry(
        call_fn=_call,
        must_contain='"verdict"',
        fallback={
            "verdict": "approve",
            "redlines": ["[review failed to parse after one retry]"],
            "revised_proposals": None,
            "_parse_error": True,
        },
    )
    return parsed


def _validate_architectural(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop architectural proposals missing required fields. The Coder's
    parser also checks Principle/What/Why/Effort/Payoff in the markdown
    persistence; a malformed proposal there silently drops fields."""
    required = ("name", "principle", "what", "why")
    return [p for p in items if all(p.get(k) for k in required)]


def _finalize(
    *,
    student_parsed: dict[str, Any],
    review: dict[str, Any],
    consulted: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Apply review verdict → final {proposals, architectural_proposals}."""
    revised = review.get("revised_proposals")
    verdict = (review.get("verdict") or "approve").lower()

    if verdict == "reject":
        return {"proposals": [], "architectural_proposals": []}

    if verdict == "revise" and isinstance(revised, dict):
        proposals = revised.get("proposals", []) or []
        arch = revised.get("architectural_proposals", []) or []
    else:
        proposals = student_parsed.get("proposals", []) or []
        arch = student_parsed.get("architectural_proposals", []) or []

    if not isinstance(proposals, list):
        proposals = []
    if not isinstance(arch, list):
        arch = []

    proposals = _ensure_lit_context(proposals, consulted)
    arch = _validate_architectural(_ensure_lit_context(arch, consulted))
    return {"proposals": proposals, "architectural_proposals": arch}


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------


def propose(
    *,
    paths: LabPaths,
    context_dir: str | Path,
    budget: BudgetTracker,
    client: anthropic.Anthropic,
    model: str | None = None,        # student override (legacy callers)
    max_tokens: int = 4096,
    mode: str = "refine",
    student_id: str | None = None,
) -> dict[str, Any]:
    """One Researcher iteration. Internally runs the Student↔Supervisor dialogue.

    Phase B: `student_id` selects which student's slice of state.json drives
    saturation streak / consecutive-empty / last_researcher_ts. Defaults to
    auto_qml.lab.DEFAULT_STUDENT_ID; with one student configured, this is
    transparent (the primary student reads/writes the legacy flat keys).

    Each proposal is tagged with `student_id` so the Executor can stamp
    runs.student_id when it executes.

    Return shape mirrors the legacy contract so the orchestrator is unchanged:
        {"proposals": [...], "architectural_proposals": [...],
         "consulted_topic_ids": [...], "raw": str, ...}
    """
    if student_id is None:
        student_id = _lab.DEFAULT_STUDENT_ID

    state = load_state(paths.state)
    sstate = StudentStateView(state, student_id)
    streak = int(sstate.get("supervisor_opus_streak", 0))
    consecutive_empty = int(sstate.get("researcher_consecutive_empty", 0))

    # Build shared context once.
    ctx = read_context(context_dir)
    rows = recent_runs(paths.runs_db, n=30)
    librarian.init_kb(paths.kb_db)
    kb_index = librarian.index_for_prompt(paths.kb_db, n=40)
    static_block = _shared_static_block(
        vision=ctx.get("vision.md", ""),
        decisions=ctx.get("decisions.md", ""),
    )
    dynamic_block = _shared_dynamic_block(
        research_log=ctx.get("research_log.md", ""),
        runs_table=_format_recent_runs(rows),
        notebook=notebook_tail(paths.notebook, max_chars=6000),
    )
    kb_index_block = _kb_block(kb_index)

    saturation = _saturation_report(paths)
    coder_log = _coder_log_tail(paths, n=10)
    student_model = model or model_for("student") or "claude-sonnet-4-6"
    sup_model = model_for_supervisor(streak)

    spend_start = budget.spend_today()

    # --- Circuit breaker: too many empty rounds → bypass Supervisor ---
    bypass_supervisor = consecutive_empty >= EMPTY_FALLBACK_THRESHOLD
    if bypass_supervisor:
        notebook_append(
            paths.notebook,
            f"## {now_iso()} — Researcher fallback: Supervisor bypassed after "
            f"{consecutive_empty} consecutive empty rounds.\n",
        )

    # --- Turn 1: Supervisor brief ---
    if bypass_supervisor:
        brief = {
            "open_questions": [],
            "forbidden_axes": [],
            "encouraged_paradigms": [],
            "expected_proposal_shape": "architectural",
            "post_mortem": "[bypass: supervisor disabled this iteration]",
        }
    else:
        brief = _supervisor_brief(
            client=client, paths=paths, budget=budget, sup_model=sup_model,
            static_block=static_block, kb_index_block=kb_index_block,
            dynamic_block=dynamic_block, saturation=saturation,
            coder_log=coder_log, mode=mode, student_id=student_id,
        )

    # --- Turn 2: Student propose ---
    student_text, student_parsed, consulted = _student_propose(
        client=client, paths=paths, budget=budget, student_model=student_model,
        static_block=static_block, kb_index_block=kb_index_block,
        dynamic_block=dynamic_block, brief=brief, max_tokens=max_tokens,
        mode=mode, student_id=student_id,
    )

    # --- Cost guardrail before Turn 3 ---
    spend_after_student = budget.spend_today()
    over_cap = (spend_after_student - spend_start) >= PER_CALL_COST_CAP_USD

    # --- Turn 3: Supervisor review ---
    if bypass_supervisor or over_cap:
        review = {
            "verdict": "approve",
            "redlines": [
                "[skipped: " + ("cost cap" if over_cap else "supervisor bypass") + "]"
            ],
            "revised_proposals": None,
        }
    else:
        review = _supervisor_review(
            client=client, paths=paths, budget=budget, sup_model=sup_model,
            static_block=static_block, student_parsed=student_parsed,
            saturation=saturation,
        )

    final = _finalize(
        student_parsed=student_parsed, review=review, consulted=consulted,
    )

    # --- Phase A: handle new_campaign + ≤2 cap, gate via popper. ---
    # new_campaign is sourced from the Student turn only — the Supervisor's
    # revised_proposals can rewrite proposals but cannot redact a campaign
    # declaration. The Student is the only role that opens campaigns.
    new_campaign = student_parsed.get("new_campaign")
    try:
        # Per-student cap (Phase B): each student gets MAX_OPEN_CAMPAIGNS_PER_STUDENT,
        # so Student A's open campaigns don't block Student B from opening their own.
        opens = _campaign_open_list_for_student(
            paths.runs_db, _lab.LAB_ID, student_id,
        )
    except sqlite3.OperationalError:
        # campaigns table absent (pre-migration DB); treat as zero open campaigns.
        opens = []
    new_campaign_id: str | None = None
    if new_campaign and len(opens) < _lab.MAX_OPEN_CAMPAIGNS_PER_STUDENT:
        slug = _slugify(new_campaign.get("question", "campaign"))[:48] + "-" + uuid.uuid4().hex[:6]
        # Per-student popper-corpus subdir. Primary keeps the legacy unsuffixed
        # path (popper-corpus/<slug>) so existing hypotheses don't move; siblings
        # land under popper-corpus/<student_id>/<slug>.
        if student_id == _lab.DEFAULT_STUDENT_ID:
            corpus_root = paths.root.parent / "popper-corpus"
        else:
            corpus_root = paths.root.parent / "popper-corpus" / student_id
        gate_result = _popper_gate.run_gate(
            draft_claim=new_campaign.get("draft_hypothesis", ""),
            slug=slug,
            corpus_root=corpus_root,
            client=client,
        )
        if gate_result.ok:
            campaign_id = "c-" + uuid.uuid4().hex[:10]
            _campaign_insert(
                paths.runs_db,
                id=campaign_id,
                lab_id=_lab.LAB_ID,
                question=new_campaign.get("question", ""),
                hypothesis_path=str(gate_result.path.relative_to(paths.root.parent)),
                hypothesis_hash=gate_result.hash,
                student_id=student_id,
            )
            new_campaign_id = campaign_id
            notebook_append(
                paths.notebook,
                f"## {now_iso()} — opened campaign {campaign_id} "
                f"({new_campaign.get('question')!r}) hash={gate_result.hash[:14]}...\n",
            )
        else:
            notebook_append(
                paths.notebook,
                f"## {now_iso()} — popper-gate REJECTED draft hypothesis: "
                f"{gate_result.reason}\n",
            )

    # Route proposals: only when the student declared a new_campaign (or
    # proposals carry explicit campaign_ids). If the student emitted neither,
    # proposals are passed through as-is (backward-compatible path).
    if new_campaign is not None:
        final_proposals: list[dict] = []
        for p in final.get("proposals", []):
            if p.get("campaign_id") is None:
                if new_campaign_id is not None:
                    p["campaign_id"] = new_campaign_id
                else:
                    notebook_append(
                        paths.notebook,
                        f"## {now_iso()} — dropped untagged proposal {p.get('name')!r}\n",
                    )
                    continue
            final_proposals.append(p)
        final["proposals"] = final_proposals

    # --- Tag proposals with the mode + student_id ---
    for p in final["proposals"]:
        p["mode"] = mode
        p.setdefault("student_id", student_id)
    for p in final["architectural_proposals"]:
        p.setdefault("student_id", student_id)

    # --- Persist architectural proposals (Coder reads this file) ---
    if final["architectural_proposals"]:
        from efferents.agents.coder import proposed_changes_path as _proposed_changes_path
        _persist_architectural(
            _proposed_changes_path(paths, student_id),
            final["architectural_proposals"],
        )

    # --- Persist foundational_external dependencies (Phase D reproduction
    # discipline). Each proposal that declares a foundational dependency on
    # an external paper writes one line to lab/foundational_deps.jsonl so
    # the next Supervisor brief can surface what's still unverified. The
    # reproduction itself is the Student's own follow-up — see student.md.
    deps_log = paths.root / "foundational_deps.jsonl"
    deps_ts = now_iso()
    for p in final["proposals"] + final["architectural_proposals"]:
        deps = p.get("foundational_external") or []
        if not isinstance(deps, list):
            continue
        for dep in deps:
            if not isinstance(dep, dict):
                continue
            lab_id = dep.get("lab_id")
            cid = dep.get("campaign_id")
            if not lab_id or not cid:
                continue
            append_jsonl(deps_log, {
                "ts": deps_ts,
                "lab_id": lab_id,
                "campaign_id": cid,
                "why": dep.get("why", ""),
                "proposal_name": p.get("name", "?"),
                "student_id": student_id,
            })

    # --- Update state cursors (per-student) ---
    is_empty = not (final["proposals"] or final["architectural_proposals"])
    sstate["researcher_consecutive_empty"] = (consecutive_empty + 1) if is_empty else 0
    sstate["supervisor_opus_streak"] = (
        (streak + 1) if saturation["score"] >= 1 else 0
    )
    sstate["last_researcher_ts"] = now_iso()
    save_state(paths.state, state)

    # --- Observability ---
    append_jsonl(paths.root / "researcher_dialogue.jsonl", {
        "ts": now_iso(),
        "saturation": saturation,
        "supervisor_opus_streak_before": streak,
        "supervisor_model": sup_model,
        "student_model": student_model,
        "bypass_supervisor": bypass_supervisor,
        "over_cost_cap": over_cap,
        "spend_delta_usd": round(spend_after_student - spend_start, 4),
        "brief": brief,
        "student_parse_error": bool(student_parsed.get("_parse_error")),
        "review_verdict": review.get("verdict"),
        "review_redlines": review.get("redlines"),
        "n_proposals": len(final["proposals"]),
        "n_architectural": len(final["architectural_proposals"]),
    })

    return {
        "proposals": final["proposals"],
        "architectural_proposals": final["architectural_proposals"],
        "consulted_topic_ids": consulted,
        "raw": student_text,
        "supervisor_brief": brief,
        "supervisor_review": review,
        "saturation": saturation,
    }
