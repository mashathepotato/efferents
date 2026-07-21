"""Build the shared journal index for the Challengescape multi-lab demo.

Deterministic, no LLM calls: walks each lab under labs/, reads its
efferents.yaml, runs.jsonl, and journal entries, plus the cross-lab reviews
under shared_journal/reviews/, and renders shared_journal/index.md. Rerunning
after `launch_overnight.sh` always reproduces the same index from the same
artifacts.

Usage: python crosslab.py   (from examples/challengescape/, inside the
project venv — needs pyyaml, which efferents already depends on)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
LABS = ROOT / "labs"
SHARED = ROOT / "shared_journal"

HONESTY = (
    "> **What is real here:** every experiment, metric, and run record in "
    "these journals was produced by `efferents run` executing each lab's own "
    "train/eval commands, offline and deterministically — rerun "
    "`launch_overnight.sh` to reproduce them. Hypothesis framing, reviewer "
    "notes, and cross-lab reviews were written by an LLM agent pass grounded "
    "in those recorded runs; every quantitative claim cites a run_id. "
    "Nothing here is a scientific result — it is a demonstration of "
    "autonomous research memory, review, and inter-lab transfer on real "
    "challenge framings from Encode's public "
    "[Challengescape](https://encode-challengescape.pillar.vc/)."
)


def _read_runs(lab_dir: Path) -> list[dict]:
    runs_file = lab_dir / "out" / "runs.jsonl"
    if not runs_file.is_file():
        return []
    return [json.loads(line) for line in runs_file.read_text().splitlines() if line.strip()]


def _frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    return yaml.safe_load(m.group(1)) if m else {}


def _verdict(path: Path) -> str:
    m = re.search(r"\*\*Verdict: (.*?)\*\*", path.read_text(), re.DOTALL)
    return " ".join(m.group(1).split()).rstrip(".") if m else "—"


def _lab_section(lab_dir: Path) -> tuple[str, str]:
    cfg = yaml.safe_load((lab_dir / "efferents.yaml").read_text())
    runs = _read_runs(lab_dir)
    metric, maximize = cfg["metric"], cfg.get("maximize", True)
    name = lab_dir.name
    rel = f"../labs/{name}"  # links resolve relative to shared_journal/index.md

    best = None
    if runs:
        best = (max if maximize else min)(runs, key=lambda r: r[metric])

    journal = sorted((lab_dir / "out" / "journal").glob("*.md")) if (lab_dir / "out" / "journal").is_dir() else []
    review = lab_dir / "out" / "journal" / "005_review.md"
    verdict = _verdict(review) if review.is_file() else "not yet reviewed"

    summary_row = (
        f"| [{name}]({rel}/challenge.md) | `{metric}` "
        f"({'max' if maximize else 'min'}) | "
        + (f"**{best[metric]}** at `{best['param']}={best['value']}` (`{best['run_id']}`)" if best else "no runs")
        + f" | {len(runs)} | {verdict} |"
    )

    lines = [f"## {name}", ""]
    lines.append(f"**Goal:** {' '.join(str(cfg['goal']).split())}")
    lines.append("")
    if best:
        lines.append(
            f"**Best run:** `{best['run_id']}` — {metric}={best[metric]} at "
            f"`{best['param']}={best['value']}` "
            f"([log]({rel}/out/{best['log_path']}))"
        )
        lines.append("")
        lines.append(f"| run_id | {best['param']} | {metric} |")
        lines.append("|--------|------|------|")
        for r in runs:
            mark = " ◀ best" if r["run_id"] == best["run_id"] else ""
            lines.append(f"| {r['run_id']} | {r['value']} | {r[metric]}{mark} |")
        lines.append("")
    lines.append(f"**Review verdict:** {verdict} ([full review]({rel}/out/journal/005_review.md))")
    lines.append("")
    lines.append(
        "**Artifacts:** "
        + " · ".join(f"[{p.name}]({rel}/out/journal/{p.name})" for p in journal)
        + f" · [runs.jsonl]({rel}/out/runs.jsonl)"
        + f" · [claims.jsonl]({rel}/out/claims.jsonl)"
        + f" · [dashboard]({rel}/out/dashboard.html)"
        + f" · [questions for the challenge POC]({rel}/questions_for_poc.md)"
    )
    lines.append("")
    return summary_row, "\n".join(lines)


def main() -> None:
    lab_dirs = sorted(d for d in LABS.iterdir() if d.is_dir())
    rows, sections = [], []
    for lab_dir in lab_dirs:
        row, section = _lab_section(lab_dir)
        rows.append(row)
        sections.append(section)

    review_lines = []
    for review in sorted((SHARED / "reviews").glob("*.md")):
        fm = _frontmatter(review)
        status = fm.get("status", "")
        review_lines.append(
            f"- [`{review.name}`](reviews/{review.name}) — "
            f"**{fm.get('reviewer_lab', '?')}** reviews "
            f"**{fm.get('reviewed_lab', '?')}**"
            + (f" — *{status}*" if status else "")
        )

    out = [
        "# Shared journal — three interconnected Challengescape labs",
        "",
        HONESTY,
        "",
        "## Labs at a glance",
        "",
        "| lab | headline metric | best result | runs | review verdict |",
        "|-----|-----------------|-------------|------|----------------|",
        *rows,
        "",
        "## Cross-lab reviews",
        "",
        *review_lines,
        "",
        "**The transfer that closed the loop:** Lab 01's window-ceiling and "
        "temporal-signature findings ([review](reviews/lab_01_on_lab_03.md)) "
        "caused Lab 03 to withdraw its planned next experiment and adopt a "
        "storm-trend feature with ceiling-aware window bounds — see "
        "[006_next_experiment_v2.md]"
        "(../labs/lab_03_local_risk/out/journal/006_next_experiment_v2.md).",
        "",
        *sections,
    ]
    SHARED.mkdir(exist_ok=True)
    (SHARED / "index.md").write_text("\n".join(out) + "\n")
    print(f"wrote {SHARED / 'index.md'} ({len(lab_dirs)} labs, {len(review_lines)} cross-lab reviews)")


if __name__ == "__main__":
    main()
