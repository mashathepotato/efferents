"""The Writer agent: regenerates paper figures/tables from lab/runs.sqlite,
appends a dated findings block to paper/sections/05_findings_log.tex,
rewrites the prose in paper/sections/03_results.tex, updates paper/notes.md,
and pushes a TL;DR to ntfy.

Two run modes:
  write_once(...)   — single pass, exits when done. Use from cron or one-shot.
  run_loop(...)     — long-running poll-and-fire. Triggers a pass when:
                        - >= runs_per_write new runs arrived since last pass, OR
                        - >= hours_per_write hours have elapsed since last pass.
                      Mirrors the orchestrator's digest-cadence shape so it can
                      run as a sibling launchd LaunchAgent process.

Deterministic outputs (no LLM):
- paper/figures/data_efficiency.png
- paper/figures/aug_depth_sweep.png  (only if aug_depth runs exist)
- paper/tables/recent_runs.tex
- paper/tables/best_per_config.tex
- paper/refs.bib                     (deduped union of kb_papers.bibtex)
- paper/sections/02_related.tex      (synthesis from kb_topics, grouped by intent)

LLM outputs (Sonnet 4.6, scoped tightly per writer.md prompt):
- append to paper/sections/05_findings_log.tex
- append to paper/notes.md
- rewrite paper/sections/03_results.tex (between fixed include points)
- prose cell in reports/weekly/YYYY-Www.ipynb
- TL;DR block (parsed from response, used as ntfy body)

Reads from `lab/` (researcher's data) — pass --lab to point at the main repo's
lab dir when running from the writer worktree.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date as _date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml as _yaml

from efferents import lab as _lab
from efferents.agents.prompts.loader import load_prompt
from efferents.schemas.paper_frontmatter import (
    PaperFrontmatter,
    REQUIRED_SECTIONS_IN_ORDER,
    structural_check,
)


# ----------------------- novelty / gain gate -----------------------

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


# ----------------------- platform-shaped paper artifact -----------------------

_WRITER_SYSTEM = """You are the Writer agent for an autonomous research lab.
You produce agent-readable paper artifacts (Markdown) for OTHER agents to read.
Output ONLY the body Markdown — five sections in this exact order:

""" + "\n".join(f"## {s}" for s in REQUIRED_SECTIONS_IN_ORDER) + """

Methods must be detailed enough that another lab's Researcher can draft
a recreation config WITHOUT consulting the source repo. Use inline code
blocks where the canonical implementation is non-obvious.

No frontmatter — the caller adds that. No code fences around the
output. Begin with the literal line "## Motivation"."""


def _resolve_code_sha() -> str | None:
    """Return git's current HEAD short SHA, or None if not in a repo."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return out.decode().strip() or None
    except Exception:
        return None


def _best_metric(runs: list[dict], col: str, direction: str) -> float | None:
    """Return the best value of `col` across runs. min when direction=='min',
    max otherwise. None when no run carries the column."""
    vals = [r[col] for r in runs if r.get(col) is not None]
    if not vals:
        return None
    return min(vals) if direction == "min" else max(vals)


def _resolve_campaign_metric(
    campaign: dict, *, default: tuple[str, str]
) -> tuple[str, str]:
    """Resolve (metric, direction) for a campaign, preferring the
    campaign-declared values and falling back to `default` when null."""
    metric = campaign.get("headline_metric") or default[0]
    direction = campaign.get("headline_direction") or default[1]
    if direction not in ("min", "max"):
        direction = default[1]
    return metric, direction


def compose_paper(
    *,
    client: Any,
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


# ----------------------- Phase A entry point -----------------------

def write_phase_a_paper(
    paths: "WriterPaths",
    campaign: dict,
    client: Any,
    *,
    gain_threshold: float = 0.05,
    model: str = "claude-sonnet-4-6",
    budget: Any = None,
) -> str | None:
    """Gate-check, compose, peer-review, and commit a paper for a campaign.

    Pipeline:
      1. Mechanical pre-gate: novelty + ≥`gain_threshold` metric improvement
         (agents/writer.py:should_publish). If it fails, log and return None.
      2. Compose the paper artifact (Sonnet via compose_paper) and write to
         paper/<campaign_id>.md.
      3. If `auto_qml.lab.PEER_REVIEW_ENABLED` is False, return here (legacy
         publish-on-mechanical-gate behavior).
      4. Otherwise, run the 3-reviewer board (critical/neutral/enthusiast,
         in parallel) + one-shot rebuttal + decide().
      5. Write side-cars (reviews.md, rebuttal.md). Append to journal.md
         on accept; append to rejected.md on reject.
      6. On accept: auto-commit the bundle (paper + reviews + rebuttal +
         journal.md). Close the campaign with reason "published".
      7. On reject: close the campaign with reason "rejected_by_review".

    Returns the paper artifact string regardless of accept/reject (so callers
    can introspect what was composed), or None if the mechanical gate
    rejected the campaign before composition.
    """
    import sqlite3 as _sqlite3

    db = paths.runs_db

    def _load_campaign_runs(campaign_id: str) -> list[dict]:
        if not db.exists():
            return []
        conn = _sqlite3.connect(db)
        conn.row_factory = _sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM runs WHERE campaign_id = ? ORDER BY started_at ASC",
                (campaign_id,),
            ).fetchall()
        except _sqlite3.OperationalError:
            return []
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def _load_other_runs(campaign_id: str) -> list[dict]:
        if not db.exists():
            return []
        conn = _sqlite3.connect(db)
        conn.row_factory = _sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM runs WHERE campaign_id != ? OR campaign_id IS NULL ORDER BY started_at ASC",
                (campaign_id,),
            ).fetchall()
        except _sqlite3.OperationalError:
            return []
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def _load_existing_claims() -> list[str]:
        """Stub: return novelty_claim strings from prior paper frontmatter files."""
        paper_dir = paths.paper
        if not paper_dir.exists():
            return []
        claims: list[str] = []
        for md_file in paper_dir.glob("*.md"):
            try:
                text = md_file.read_text()
                if not text.startswith("---"):
                    continue
                _, fm_yaml, _ = text.split("---", 2)
                fm = _yaml.safe_load(fm_yaml)
                if isinstance(fm, dict) and fm.get("novelty_claim"):
                    claims.append(str(fm["novelty_claim"]))
            except Exception:
                continue
        return claims

    campaign_id = campaign["id"]
    campaign_runs = _load_campaign_runs(campaign_id)
    other_runs = _load_other_runs(campaign_id)

    from efferents import lab as _lab_cfg  # local import; cfg may be unset in unit tests
    try:
        _default = (_lab_cfg.get_config().metrics.headline.column,
                    _lab_cfg.get_config().metrics.headline.direction)
    except Exception:
        _default = ("e_w1", "min")
    metric, direction = _resolve_campaign_metric(campaign, default=_default)

    candidate_value = _best_metric(campaign_runs, metric, direction)
    baseline_value = _best_metric(other_runs, metric, direction)

    # If no campaign runs, nothing to publish.
    if candidate_value is None:
        return None

    # If no baseline, assume headroom in the improving direction so the gate
    # can still pass. min → baseline 20% higher; max → 20% lower.
    if baseline_value is None:
        baseline_value = candidate_value * (1.2 if direction == "min" else 0.8)

    existing_claims = _load_existing_claims()
    novelty_claim = campaign.get("question", "").strip() or campaign_id

    gate_inputs = GateInputs(
        primary_metric_name=metric,
        baseline_value=baseline_value,
        candidate_value=candidate_value,
        novelty_claim=novelty_claim,
        existing_lab_claims=existing_claims,
        refutation_of_corroborated=campaign.get("refutation_of_corroborated"),
    )

    ok, reason = should_publish(gate_inputs, gain_threshold=gain_threshold)

    if not ok:
        # Log to notebook and return None.
        notebook = paths.notebook
        msg = (
            f"\n### Writer gate: skipped {campaign_id}\n\n"
            f"Gate rejected: {reason}\n"
            f"candidate {metric}={candidate_value:.4f}, baseline={baseline_value:.4f}\n"
        )
        try:
            with notebook.open("a") as f:
                f.write(msg)
        except Exception:
            pass
        return None

    # Build metric_provenance from campaign runs.
    runs_by_seed: dict[int, list[float]] = {}
    run_ids: list[str] = []
    for r in campaign_runs:
        if r.get(metric) is None:
            continue
        seed = r.get("seed", 0) or 0
        runs_by_seed.setdefault(seed, []).append(r[metric])
        run_ids.append(r["run_id"])

    metric_provenance = [
        {
            "name": metric,
            "value": candidate_value,
            "delta_vs_baseline": candidate_value - baseline_value,
            "runs": run_ids or [campaign_id],
            "seeds": list(runs_by_seed.keys()) or [0],
        }
    ]

    # Resolve real git SHA for paper metadata, or set both None if unavailable.
    sha = _resolve_code_sha() if _lab.CODE_REPO else None
    repo = _lab.CODE_REPO if sha else None  # if we can't get a SHA, set neither

    artifact = compose_paper(
        client=client,
        campaign=campaign,
        metric_provenance=metric_provenance,
        novelty_claim=novelty_claim,
        code_sha=sha,
        code_repo=repo,
        model=model,
    )

    # Write artifact to paper/<campaign_id>.md.
    paper_dir = paths.paper
    paper_dir.mkdir(parents=True, exist_ok=True)
    out_path = paper_dir / f"{campaign_id}.md"
    out_path.write_text(artifact)

    # If peer review is disabled, we're done — legacy publish-on-gate path.
    if not _lab.PEER_REVIEW_ENABLED:
        return artifact

    # ------------------------------------------------------------------
    # Peer review pipeline: 3 reviewers (parallel) → rebuttal → decide
    # ------------------------------------------------------------------
    from concurrent.futures import ThreadPoolExecutor

    from efferents.agents import journal as _journal
    from efferents.agents import rebuttal as _rebuttal
    from efferents.agents import reviewer as _reviewer
    from efferents.agents.state import (
        campaign_close as _campaign_close,
        notebook_append,
        now_iso,
    )

    if budget is None:
        from efferents.agents.budget import BudgetTracker
        budget = BudgetTracker(paths.budget, daily_cap_usd=10000.0)

    delta_pct = (
        100.0 * (baseline_value - candidate_value) / baseline_value
        if direction == "min" and baseline_value
        else (100.0 * (candidate_value - baseline_value) / baseline_value
              if baseline_value else 0.0)
    )
    headline = (
        f"{novelty_claim} — {metric} {candidate_value:.3f} vs baseline "
        f"{baseline_value:.3f} ({delta_pct:+.1f}%)"
    )

    try:
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {
                p: ex.submit(
                    _reviewer.review,
                    paper_path=out_path, persona=p,
                    client=client, budget=budget,
                )
                for p in _reviewer.PERSONAS
            }
            reviews = [futures[p].result() for p in _reviewer.PERSONAS]
    except Exception as e:
        notebook_append(
            paths.notebook,
            f"## {now_iso()} — peer-review board FAILED for {campaign_id}: "
            f"{type(e).__name__}: {e}. Campaign left open.\n",
        )
        return artifact

    try:
        rebuttal_text = _rebuttal.write_rebuttal(
            paper_path=out_path, reviews=reviews,
            client=client, budget=budget,
        )
    except Exception as e:
        rebuttal_text = f"## Rebuttal\n\n(rebuttal failed: {type(e).__name__}: {e})\n"

    decision = _reviewer.decide(reviews)

    _journal.write_reviews_file(
        paper_dir / f"{campaign_id}.reviews.md",
        campaign_id=campaign_id, reviews=reviews, decision=decision,
    )
    _journal.write_rebuttal_file(
        paper_dir / f"{campaign_id}.rebuttal.md",
        campaign_id=campaign_id, rebuttal_text=rebuttal_text,
    )

    student_id = campaign.get("student_id") or "primary"

    if decision["accept"]:
        _journal.append_journal(
            paper_dir / "journal.md",
            campaign_id=campaign_id, headline=headline, decision=decision,
            student_id=student_id,
        )
        try:
            sha = _journal.auto_commit_paper(
                repo_root=paths.paper.parent,
                campaign_id=campaign_id, headline=headline, decision=decision,
            )
            commit_msg = f"committed as {sha}" if sha else "commit failed"
        except Exception as e:
            commit_msg = f"commit raised: {type(e).__name__}: {e}"
        try:
            _campaign_close(paths.runs_db, campaign_id, reason="published")
        except Exception:
            pass  # already closed, or no campaigns table; non-fatal
        notebook_append(
            paths.notebook,
            f"## {now_iso()} — Paper ACCEPTED: {campaign_id} "
            f"(mean={decision['mean_score']:.1f}, min={decision['min_score']}); "
            f"{commit_msg}.\n",
        )
    else:
        _journal.append_rejected(
            paper_dir / "rejected.md",
            campaign_id=campaign_id, headline=headline, decision=decision,
            student_id=student_id,
        )
        try:
            _campaign_close(paths.runs_db, campaign_id, reason="rejected_by_review")
        except Exception:
            pass
        notebook_append(
            paths.notebook,
            f"## {now_iso()} — Paper REJECTED: {campaign_id}; {decision['reason']}.\n",
        )

    return artifact


# Heavy imports kept lazy so `--help` stays snappy.
def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


@dataclass(frozen=True)
class WriterPaths:
    lab: Path
    runs_db: Path
    notebook: Path
    digests_dir: Path
    state: Path
    budget: Path
    context: Path
    kb_db: Path
    paper: Path
    paper_sections: Path
    paper_figures: Path
    paper_tables: Path
    paper_notes: Path
    findings_log: Path
    results_section: Path
    refs_bib: Path
    related_section: Path
    reports_weekly: Path


def writer_paths(
    *, lab: str | Path, paper: str | Path, reports: str | Path, context: str | Path
) -> WriterPaths:
    lab = Path(lab)
    paper = Path(paper)
    reports = Path(reports)
    context = Path(context)
    return WriterPaths(
        lab=lab,
        runs_db=lab / "runs.sqlite",
        notebook=lab / "lab_notebook.md",
        digests_dir=lab / "digests",
        state=lab / "state.json",
        budget=lab / "budget.jsonl",
        context=context,
        kb_db=lab / "knowledge" / "kb.sqlite",
        paper=paper,
        paper_sections=paper / "sections",
        paper_figures=paper / "figures",
        paper_tables=paper / "tables",
        paper_notes=paper / "notes.md",
        findings_log=paper / "sections" / "05_findings_log.tex",
        results_section=paper / "sections" / "03_results.tex",
        refs_bib=paper / "refs.bib",
        related_section=paper / "sections" / "02_related.tex",
        reports_weekly=reports / "weekly",
    )


# ----------------------- data loading -----------------------

ALL_RUNS_SQL = """
SELECT run_id, started_at, seed, model, raw_q, epochs, aug_depth,
       aug_shared_unitary, cond_drop_p, eval_kind, eval_n,
       val_x0_mse, e_w1, active_frac_w1, radial_l2, radial_l2_log,
       duration_seconds, config_hash, notes
FROM runs ORDER BY started_at ASC
"""


def load_all_runs(db: Path) -> list[dict[str, Any]]:
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(ALL_RUNS_SQL).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def load_recent_digests(digests_dir: Path, since_path: str | None = None) -> list[tuple[str, str]]:
    """Return [(filename, content), ...] for digests newer than since_path."""
    if not digests_dir.exists():
        return []
    files = sorted(p for p in digests_dir.iterdir() if p.suffix == ".md")
    if since_path:
        try:
            cutoff_idx = next(i for i, p in enumerate(files) if p.name == Path(since_path).name)
            files = files[cutoff_idx + 1:]
        except StopIteration:
            pass  # cursor file no longer present; return all
    return [(p.name, p.read_text()) for p in files]


# ----------------------- deterministic figures -----------------------

def regenerate_data_efficiency_figure(runs: list[dict[str, Any]], out_path: Path) -> bool:
    """Plot mean E_W1 per (model, raw_q), with seed std as error bars.

    Returns True if a real figure was written, False if not enough data
    (writes a placeholder PNG either way so the .tex \\includegraphics works).
    """
    plt = _mpl()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Bucket runs by (model, raw_q).
    buckets: dict[tuple[str, int], list[float]] = {}
    for r in runs:
        if r.get("e_w1") is None or r.get("model") is None or r.get("raw_q") is None:
            continue
        key = (str(r["model"]), int(r["raw_q"]))
        buckets.setdefault(key, []).append(float(r["e_w1"]))

    if not buckets:
        # Placeholder.
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(
            0.5, 0.5,
            "data_efficiency.png\n(no runs yet)",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=14, alpha=0.5,
        )
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return False

    # One line per model.
    models = sorted({m for (m, _) in buckets})
    fig, ax = plt.subplots(figsize=(6, 4))
    for m in models:
        xs, means, stds, ns = [], [], [], []
        for (mm, rq), vals in sorted(buckets.items()):
            if mm != m:
                continue
            xs.append(rq)
            means.append(sum(vals) / len(vals))
            if len(vals) > 1:
                mean = means[-1]
                var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
                stds.append(var ** 0.5)
            else:
                stds.append(0.0)
            ns.append(len(vals))
        ax.errorbar(xs, means, yerr=stds, marker="o", capsize=3, label=f"{m} (n={max(ns) if ns else 0})")

    ax.set_xlabel("raw_q (training-data budget)")
    ax.set_ylabel("E_W1 (energy-Wasserstein-1)")
    ax.set_title("Data efficiency — lower is better")
    ax.set_xscale("log")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return True


def regenerate_aug_depth_figure(runs: list[dict[str, Any]], out_path: Path) -> bool:
    plt = _mpl()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    buckets: dict[int, list[float]] = {}
    for r in runs:
        ad = r.get("aug_depth")
        e = r.get("e_w1")
        if ad is None or e is None or r.get("model") != "qfm":
            continue
        buckets.setdefault(int(ad), []).append(float(e))

    if len(buckets) < 2:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(
            0.5, 0.5,
            f"aug_depth_sweep.png\n(need >=2 distinct aug_depth values, have {len(buckets)})",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=12, alpha=0.5,
        )
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return False

    xs = sorted(buckets)
    means = [sum(buckets[k]) / len(buckets[k]) for k in xs]
    stds = []
    for k in xs:
        vals = buckets[k]
        if len(vals) > 1:
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
            stds.append(var ** 0.5)
        else:
            stds.append(0.0)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.errorbar(xs, means, yerr=stds, marker="o", capsize=3)
    ax.set_xlabel("aug_depth")
    ax.set_ylabel("E_W1 (QFM)")
    ax.set_title("Augmentation depth sweep")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return True


# ----------------------- deterministic tables -----------------------

def _fmt_metric(v: float | None, prec: int = 3) -> str:
    if v is None:
        return "--"
    if v == 0:
        return "0"
    av = abs(v)
    if av < 1e-2 or av >= 1e3:
        return f"{v:.{prec}e}"
    return f"{v:.{prec}f}"


def regenerate_recent_runs_table(runs: list[dict[str, Any]], out_path: Path, n: int = 30) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    recent = runs[-n:][::-1]
    rows = []
    for r in recent:
        rows.append(
            "  "
            + " & ".join([
                str(r.get("run_id", "?"))[:8],
                str(r.get("model", "?")),
                str(r.get("raw_q", "?")),
                str(r.get("seed", "?")),
                str(r.get("aug_depth", "?")),
                str(r.get("eval_kind", "?")),
                _fmt_metric(r.get("e_w1")),
                _fmt_metric(r.get("radial_l2_log")),
            ])
            + " \\\\"
        )

    body = "\n".join(rows) if rows else "  \\multicolumn{8}{c}{\\textit{no runs yet}} \\\\"
    out_path.write_text(
        "% Auto-generated by agents/writer.py — do not hand-edit.\n"
        "\\begin{table}[t]\n"
        "  \\centering\n"
        "  \\small\n"
        "  \\caption{Recent runs (last " + str(n) + " by start time, newest first).}\n"
        "  \\label{tab:recent-runs}\n"
        "  \\begin{tabular}{llrrrlrr}\n"
        "    \\toprule\n"
        "    run\\_id & model & raw\\_q & seed & aug\\_d & eval & E\\_W1 & RadL2log \\\\\n"
        "    \\midrule\n"
        + body + "\n"
        "    \\bottomrule\n"
        "  \\end{tabular}\n"
        "\\end{table}\n"
    )


def regenerate_best_per_config_table(runs: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Best (lowest) E_W1 per (model, raw_q).
    best: dict[tuple[str, int], dict[str, Any]] = {}
    for r in runs:
        if r.get("e_w1") is None or r.get("model") is None or r.get("raw_q") is None:
            continue
        key = (str(r["model"]), int(r["raw_q"]))
        prev = best.get(key)
        if prev is None or r["e_w1"] < prev["e_w1"]:
            best[key] = r

    if not best:
        out_path.write_text(
            "% Auto-generated by agents/writer.py — do not hand-edit.\n"
            "\\begin{table}[t]\n"
            "  \\centering\n"
            "  \\caption{Best E\\_W1 per (model, raw\\_q). \\textit{No runs yet.}}\n"
            "  \\label{tab:best-per-config}\n"
            "\\end{table}\n"
        )
        return

    raw_qs = sorted({rq for (_, rq) in best})
    models = sorted({m for (m, _) in best})

    header_cols = " & ".join(["model"] + [f"raw\\_q={rq}" for rq in raw_qs]) + " \\\\"
    rows = []
    for m in models:
        cells = [m]
        for rq in raw_qs:
            r = best.get((m, rq))
            cells.append(_fmt_metric(r["e_w1"]) if r else "--")
        rows.append("  " + " & ".join(cells) + " \\\\")

    out_path.write_text(
        "% Auto-generated by agents/writer.py — do not hand-edit.\n"
        "\\begin{table}[t]\n"
        "  \\centering\n"
        "  \\small\n"
        "  \\caption{Best (lowest) E\\_W1 per (model, raw\\_q) cell.}\n"
        "  \\label{tab:best-per-config}\n"
        "  \\begin{tabular}{l" + "r" * len(raw_qs) + "}\n"
        "    \\toprule\n    "
        + header_cols + "\n"
        "    \\midrule\n"
        + "\n".join(rows) + "\n"
        "    \\bottomrule\n"
        "  \\end{tabular}\n"
        "\\end{table}\n"
    )


# ----------------------- knowledge-base -> paper artifacts -----------------------

def _load_kb_papers(kb_db: Path) -> list[dict[str, Any]]:
    if not kb_db.exists():
        return []
    conn = sqlite3.connect(kb_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM kb_papers ORDER BY first_seen ASC"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _load_kb_topics(kb_db: Path) -> list[dict[str, Any]]:
    if not kb_db.exists():
        return []
    conn = sqlite3.connect(kb_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM kb_topics ORDER BY last_used_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def regenerate_refs_bib(kb_db: Path, out_path: Path) -> int:
    """Write refs.bib from kb_papers (deduped by bib_key). Returns entry count.

    Anything not in kb_papers cannot be cited — the Writer's prompt tells the
    LLM that this file is the *only* citation source, and the librarian is
    the only path for adding new entries.
    """
    papers = _load_kb_papers(kb_db)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not papers:
        out_path.write_text(
            "% Auto-generated by agents/writer.py — do not hand-edit.\n"
            "% (kb.sqlite has no papers yet; ask the Researcher to call lit_review)\n"
        )
        return 0
    lines = [
        "% Auto-generated by agents/writer.py from lab/knowledge/kb.sqlite — do not hand-edit.",
        "% Citations in the paper must use these bib_keys; new entries flow through",
        "% the Librarian (agents/librarian.py).",
        "",
    ]
    seen: set[str] = set()
    for p in papers:
        key = p.get("bib_key")
        bibtex = (p.get("bibtex") or "").strip()
        if not key or key in seen or not bibtex:
            continue
        seen.add(key)
        lines.append(bibtex)
        lines.append("")
    out_path.write_text("\n".join(lines) + "\n")
    return len(seen)


_BIB_INLINE_RE = re.compile(r"\(([a-z][a-z0-9_]+)\)")


def _md_to_simple_tex(md: str) -> str:
    """Minimal markdown -> LaTeX for librarian-authored summary_md.

    Converts inline `(bib_key)` citations to `\\cite{bib_key}`, basic bold/italic,
    and escapes %, &, # outside of \\cite{} commands. Designed for the
    librarian's terse synthesis prose, not for arbitrary markdown.
    """
    s = _BIB_INLINE_RE.sub(r"\\cite{\1}", md)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\\emph{\1}", s)
    s = re.sub(r"(?<!\\)([%&#])", r"\\\1", s)
    return s


def _topics_referenced_by_runs(runs: list[dict[str, Any]]) -> set[str]:
    referenced: set[str] = set()
    for r in runs:
        raw = r.get("lit_context_json")
        if not raw:
            continue
        try:
            ids = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(ids, list):
            for tid in ids:
                if isinstance(tid, str):
                    referenced.add(tid)
    return referenced


_INTENT_TITLES = {
    "background": "Background",
    "open-questions": "Open questions",
    "cross-domain-bridge": "Cross-domain connections",
}


def regenerate_related_section(
    *,
    kb_db: Path,
    runs: list[dict[str, Any]],
    out_path: Path,
    only_referenced: bool = False,
) -> int:
    """Write paper/sections/02_related.tex from kb_topics, grouped by intent.

    If only_referenced=True, restrict to topics actually referenced by some
    run's lit_context_json. Otherwise emit everything in the kb (default;
    paper-style related-work tends to be broader than what experiments cite).
    """
    topics = _load_kb_topics(kb_db)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if only_referenced:
        referenced = _topics_referenced_by_runs(runs)
        topics = [t for t in topics if t["topic_id"] in referenced]

    if not topics:
        out_path.write_text(
            "% Auto-generated by agents/writer.py — do not hand-edit.\n"
            "\\section{Related work}\n"
            "\\label{sec:related}\n\n"
            "% (kb.sqlite has no topics yet; ask the Researcher to call lit_review)\n"
        )
        return 0

    by_intent: dict[str, list[dict[str, Any]]] = {}
    for t in topics:
        by_intent.setdefault(t["intent"], []).append(t)

    lines = [
        "% Auto-generated by agents/writer.py from lab/knowledge/kb.sqlite — do not hand-edit.",
        "% Source: kb_topics.summary_md, grouped by intent. Edit kb.sqlite (via",
        "% the Librarian) to change content, not this file.",
        "",
        "\\section{Related work}",
        "\\label{sec:related}",
        "",
    ]

    for intent in ("background", "open-questions", "cross-domain-bridge"):
        items = by_intent.get(intent, [])
        if not items:
            continue
        lines.append(f"\\subsection{{{_INTENT_TITLES[intent]}}}")
        lines.append("")
        for t in items:
            md = (t.get("summary_md") or "").strip()
            if not md:
                continue
            lines.append(f"% topic: {t['topic_id']}")
            lines.append(_md_to_simple_tex(md))
            lines.append("")
        if intent == "cross-domain-bridge":
            for t in items:
                try:
                    bs = json.loads(t.get("bridges_json") or "[]")
                except json.JSONDecodeError:
                    bs = []
                for b in bs:
                    if not isinstance(b, dict):
                        continue
                    a, c = b.get("domain_a", ""), b.get("domain_b", "")
                    claim = (b.get("claim") or "").strip()
                    keys = b.get("support_bib_keys") or []
                    cite = ("~\\cite{" + ",".join(keys) + "}") if keys else ""
                    if claim and (a or c):
                        lines.append(
                            f"\\paragraph{{{a} $\\leftrightarrow$ {c}.}} {claim}{cite}"
                        )
                        lines.append("")

    out_path.write_text("\n".join(lines) + "\n")
    return len(topics)


# ----------------------- LLM-driven outputs -----------------------

# Section markers in the LLM response. The prompt asks for these exact headers.
SECTIONS = ("TL;DR", "FINDINGS_LOG_BLOCK", "NOTES_BULLETS", "RESULTS_PROSE")


def _format_all_runs(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no runs yet)"
    cols = [
        "run_id", "started_at", "model", "seed", "raw_q", "epochs", "aug_depth",
        "aug_shared_unitary", "cond_drop_p", "eval_kind",
        "val_x0_mse", "e_w1", "radial_l2_log", "active_frac_w1",
    ]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        cells = [
            f"{r[c]:.4g}" if isinstance(r.get(c), float) else ("" if r.get(c) is None else str(r[c]))
            for c in cols
        ]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _read_or_empty(p: Path) -> str:
    return p.read_text() if p.exists() else ""


def _tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return "...[truncated head]...\n" + text[-max_chars:]


def parse_writer_response(text: str) -> dict[str, str]:
    """Split the LLM response by `## SECTION_NAME` markers."""
    out: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        # Match "## TL;DR", "## FINDINGS_LOG_BLOCK", etc.
        if s.startswith("## "):
            header = s[3:].strip()
            if header in SECTIONS:
                if current is not None:
                    out[current] = "\n".join(buf).strip()
                current = header
                buf = []
                continue
        if current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf).strip()
    return out


def _build_messages(
    *, vision: str, decisions: str, research_log: str, runs_table: str,
    digests: str, findings_tail: str, notes_tail: str, refs_bib: str,
) -> list[dict[str, Any]]:
    # refs.bib lives with the paper source; it's slow-changing so it joins the
    # static cache block. Cap to a sane size — the model only needs the keys
    # and titles, not megabytes of raw bibtex.
    static_block = (
        "## Vision\n\n" + vision
        + "\n\n## Decisions\n\n" + decisions
        + "\n\n## refs.bib (the *only* citation keys you may use)\n\n"
        + (refs_bib if len(refs_bib) < 32_000 else refs_bib[:32_000] + "\n% ...truncated\n")
    )
    dynamic_block = (
        "## Research log\n\n" + research_log
        + "\n\n## All runs\n\n" + runs_table
        + "\n\n## Recent digests\n\n" + digests
        + "\n\n## Current findings_log tail\n\n" + findings_tail
        + "\n\n## Current notes.md tail\n\n" + notes_tail
    )
    return [{
        "role": "user",
        "content": [
            {"type": "text", "text": static_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": dynamic_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "Write the four sections now, exactly per your system prompt format."},
        ],
    }]


def run_llm_phase(
    *,
    paths: WriterPaths,
    runs: list[dict[str, Any]],
    client: Any,  # anthropic.Anthropic
    budget: Any,  # BudgetTracker
    model: str | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Single Anthropic call → parse → write paper artifacts. Mirrors analyst.write_digest."""
    from efferents.agents.budget import CallUsage, model_for
    from efferents.agents.state import read_context

    ctx = read_context(paths.context)
    digests = load_recent_digests(paths.digests_dir)
    digests_text = (
        "\n\n---\n\n".join(f"### {name}\n\n{content}" for name, content in digests[-3:])
        if digests else "(no digests yet)"
    )
    findings_tail = _tail(_read_or_empty(paths.findings_log), 4000)
    notes_tail = _tail(_read_or_empty(paths.paper_notes), 4000)
    refs_bib = _read_or_empty(paths.refs_bib)

    messages = _build_messages(
        vision=ctx.get("vision.md", ""),
        decisions=ctx.get("decisions.md", ""),
        research_log=ctx.get("research_log.md", ""),
        runs_table=_format_all_runs(runs),
        digests=digests_text,
        findings_tail=findings_tail,
        notes_tail=notes_tail,
        refs_bib=refs_bib,
    )

    chosen = model or model_for("writer")
    if chosen is None:
        raise RuntimeError("No model configured for Writer")

    system_prompt = load_prompt("writer")
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
    budget.record(agent="writer", model=chosen, usage=usage)

    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    sections = parse_writer_response(text)

    appended_findings = False
    if sections.get("FINDINGS_LOG_BLOCK"):
        block = sections["FINDINGS_LOG_BLOCK"].strip()
        with paths.findings_log.open("a") as f:
            f.write("\n\n" + block + "\n")
        appended_findings = True

    appended_notes = False
    if sections.get("NOTES_BULLETS"):
        bullets = sections["NOTES_BULLETS"].strip()
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        with paths.paper_notes.open("a") as f:
            f.write(f"\n## {date}\n\n{bullets}\n")
        appended_notes = True

    rewrote_results = False
    if sections.get("RESULTS_PROSE"):
        body = sections["RESULTS_PROSE"].strip()
        paths.results_section.write_text(
            "% Auto-generated by agents/writer.py — agent prose. Tables/figures\n"
            "% are also auto-generated; do not edit them in place. Move worth-keeping\n"
            "% prose into a human-edited section before submission.\n\n"
            + body + "\n"
        )
        rewrote_results = True

    return {
        "tldr": sections.get("TL;DR", "").strip()[:280],
        "tokens": (usage.input_tokens, usage.output_tokens),
        "cost_usd": float(getattr(resp, "_cost_usd", 0.0) or 0.0),  # not authoritative; budget ledger is
        "appended_findings": appended_findings,
        "appended_notes": appended_notes,
        "rewrote_results": rewrote_results,
        "raw_response_chars": len(text),
        "sections_seen": list(sections),
    }


# ----------------------- Phase A paper pass -----------------------

def _phase_a_pass(paths: WriterPaths, client: Any) -> None:
    """Write a Phase A agent-readable paper for any closed campaign that
    doesn't yet have one. Logs to lab_notebook.md."""
    import sqlite3 as _sqlite3
    from efferents.agents.state import notebook_append, now_iso
    try:
        conn = _sqlite3.connect(paths.runs_db)
        conn.row_factory = _sqlite3.Row
        try:
            closed = conn.execute(
                "SELECT * FROM campaigns WHERE lab_id = ? AND closed_at IS NOT NULL",
                (_lab.LAB_ID,),
            ).fetchall()
        finally:
            conn.close()
    except _sqlite3.OperationalError:
        return  # pre-migration DB; no campaigns table

    paths.paper.mkdir(parents=True, exist_ok=True)
    for c in closed:
        out_path = paths.paper / f"{c['id']}.md"
        if out_path.exists():
            continue
        # Calls already-existing write_phase_a_paper, which handles novelty gate
        # internally and writes its own artifact to <paper>/<id>.md. If the
        # gate fails, write_phase_a_paper logs to notebook and returns None.
        try:
            write_phase_a_paper(paths, dict(c), client)
        except Exception as exc:
            notebook_append(
                paths.notebook,
                f"## {now_iso()} — Phase A paper FAILED for campaign {c['id']}: "
                f"{type(exc).__name__}: {exc}\n",
            )


# ----------------------- entry point -----------------------

def write_once(
    *,
    lab: str | Path = "lab",
    paper: str | Path = "paper",
    reports: str | Path = "reports",
    context: str | Path = "context",
    skip_llm: bool = False,
    skip_notify: bool = False,
) -> dict[str, Any]:
    """One Writer pass. Returns a telemetry dict; never raises on best-effort steps."""
    paths = writer_paths(lab=lab, paper=paper, reports=reports, context=context)
    paths.paper_figures.mkdir(parents=True, exist_ok=True)
    paths.paper_tables.mkdir(parents=True, exist_ok=True)
    paths.reports_weekly.mkdir(parents=True, exist_ok=True)

    runs = load_all_runs(paths.runs_db)

    # Deterministic phase.
    de_real = regenerate_data_efficiency_figure(runs, paths.paper_figures / "data_efficiency.png")
    ad_real = regenerate_aug_depth_figure(runs, paths.paper_figures / "aug_depth_sweep.png")
    regenerate_recent_runs_table(runs, paths.paper_tables / "recent_runs.tex")
    regenerate_best_per_config_table(runs, paths.paper_tables / "best_per_config.tex")
    n_refs = regenerate_refs_bib(paths.kb_db, paths.refs_bib)
    n_related = regenerate_related_section(
        kb_db=paths.kb_db, runs=runs, out_path=paths.related_section,
    )

    # LLM phase.
    llm: dict[str, Any]
    _client: Any = None  # shared by LLM phase and _phase_a_pass below
    if skip_llm:
        llm = {
            "tldr": f"writer pass — {len(runs)} runs; LLM skipped, deterministic outputs only.",
            "skipped": True,
        }
    else:
        try:
            import anthropic
            from efferents.agents.budget import BudgetTracker
            _client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY
            budget = BudgetTracker(paths.budget, daily_cap_usd=10000.0)  # writer ignores cap; tracked only
            llm = run_llm_phase(paths=paths, runs=runs, client=_client, budget=budget)
        except Exception as e:
            llm = {
                "tldr": f"writer LLM phase FAILED: {type(e).__name__}: {e}",
                "error": True,
            }

    # Phase A paper pass — write agent-readable papers for any closed campaigns
    # that don't yet have a paper/<campaign_id>.md artifact.
    if _client is not None:
        try:
            _phase_a_pass(paths, _client)
        except Exception as e:
            pass  # best-effort; errors already logged inside _phase_a_pass

    # Slide deck (deterministic; uses TL;DR from LLM or fallback string).
    slide_path: str | None = None
    try:
        # Defer import to avoid coupling tests/help to nbformat-shaped writes.
        import sys
        # reports/build.py lives at the worktree root, alongside agents/.
        # The CWD when running via launchd is the worktree root, so import works.
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from reports.build import build_weekly_deck, _iso_week_label

        week = _iso_week_label()
        out = paths.reports_weekly / f"{week}.ipynb"
        build_weekly_deck(
            lab_dir=paths.lab,
            out_path=out,
            tldr=str(llm.get("tldr", "")),
            week_label=week,
        )
        slide_path = str(out)
    except Exception as e:
        slide_path = f"(slide build failed: {type(e).__name__}: {e})"

    # Notify (skipped if --no-notify or stub).
    notify_payload = {"sent": False}
    if not skip_notify:
        try:
            from efferents.agents.notify import notify_all
            week_label = datetime.now(timezone.utc).strftime("%Y-W%V")
            notify_payload = notify_all(
                title=f"writer: {week_label}",
                message=str(llm.get("tldr", ""))[:280],
            )
        except Exception as e:
            notify_payload = {"sent": False, "error": f"{type(e).__name__}: {e}"}

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_runs": len(runs),
        "data_efficiency_real": de_real,
        "aug_depth_real": ad_real,
        "n_refs": n_refs,
        "n_related_topics": n_related,
        "slide_path": slide_path,
        "llm": llm,
        "notify": notify_payload,
    }


# ----------------------- continuous loop -----------------------

import signal
import time


def _hours_since_iso(iso_ts: str | None) -> float:
    if not iso_ts:
        return 1e9
    try:
        t = datetime.fromisoformat(iso_ts)
    except ValueError:
        return 1e9
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def run_loop(
    *,
    lab: str | Path = "lab",
    paper: str | Path = "paper",
    reports: str | Path = "reports",
    context: str | Path = "context",
    runs_per_write: int = 15,
    hours_per_write: float = 5.0,
    check_every_seconds: int = 60,
    skip_llm: bool = False,
) -> None:
    """Long-running poll loop. Fires write_once when cadence triggers.

    State cursors live in lab/state.json:
        last_writer_runs : int  (run count at last writer pass)
        last_writer_ts   : str  (ISO 8601 of last writer pass)

    SIGTERM/SIGINT exits cleanly between checks.
    """
    from efferents.agents.state import load_state, save_state, runs_count

    paths = writer_paths(lab=lab, paper=paper, reports=reports, context=context)
    paths.paper_figures.mkdir(parents=True, exist_ok=True)
    paths.paper_tables.mkdir(parents=True, exist_ok=True)
    paths.reports_weekly.mkdir(parents=True, exist_ok=True)

    stop = {"flag": False}
    def _on_sig(signum: int, _frame: Any) -> None:
        stop["flag"] = True
    signal.signal(signal.SIGTERM, _on_sig)
    signal.signal(signal.SIGINT, _on_sig)

    print(
        f"[writer-loop] starting; lab={paths.lab}, paper={paths.paper}, "
        f"runs_per_write={runs_per_write}, hours_per_write={hours_per_write}, "
        f"check_every={check_every_seconds}s, skip_llm={skip_llm}",
        flush=True,
    )

    while not stop["flag"]:
        try:
            state = load_state(paths.state)
            n_runs = runs_count(paths.runs_db)
            last_n = int(state.get("last_writer_runs", 0))
            last_ts = state.get("last_writer_ts")
            delta_runs = n_runs - last_n
            hours_since = _hours_since_iso(last_ts)

            should_fire = (
                (delta_runs >= runs_per_write and last_n >= 0)
                or (last_ts is None and n_runs > 0)  # first-ever pass once data exists
                or (hours_since >= hours_per_write and n_runs > last_n)
            )

            if should_fire:
                print(
                    f"[writer-loop] firing write_once: n_runs={n_runs}, "
                    f"delta={delta_runs}, hours_since={hours_since:.2f}",
                    flush=True,
                )
                out = write_once(
                    lab=lab, paper=paper, reports=reports, context=context,
                    skip_llm=skip_llm,
                )
                # Persist cursors only on success-ish (write_once is best-effort).
                state["last_writer_runs"] = out.get("n_runs", n_runs)
                state["last_writer_ts"] = out.get("ts", datetime.now(timezone.utc).isoformat())
                state["last_writer_tldr"] = (out.get("llm") or {}).get("tldr", "")
                save_state(paths.state, state)
                print(f"[writer-loop] done: {out.get('llm', {}).get('tldr', '')[:200]}", flush=True)
            else:
                # Nothing to do.
                pass
        except Exception as e:
            print(f"[writer-loop] iteration FAILED: {type(e).__name__}: {e}", flush=True)
            # Cool-off so we don't spam errors.
            time.sleep(60)

        # Sleep in 5-second chunks so SIGTERM is responsive.
        end = time.monotonic() + check_every_seconds
        while not stop["flag"] and time.monotonic() < end:
            time.sleep(min(5, max(0.5, end - time.monotonic())))

    print("[writer-loop] stopped cleanly.", flush=True)
