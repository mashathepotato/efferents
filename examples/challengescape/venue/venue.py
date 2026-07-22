"""Venue engine — submission, board review, revision, decision, reproduction.

Implements the journal-as-venue lifecycle from ``context/journal_vision.md``
(with the 2026-07-22 pre-publication-review addendum) as a file-based,
deterministic state machine:

    submitted -> under_review -> minor/major_revision -> resubmitted
              -> accepted (-> proceedings/) | rejected

Post-publication, trust is endogenous: a lab that builds on an accepted paper
runs ``venue.py reproduce`` first, which **actually re-executes** the
manuscript's reproduction recipe in a scratch directory and compares every
claimed metric within the venue margin — corroborated/challenged is a
mechanical verdict, not an opinion.

Review and decision *text* is authored by agents (or humans); this engine
validates contracts, aggregates the board's recommendations into the
deterministic decision, executes reproductions, and keeps the append-only
ledger and proceedings index.

Usage (from the repo root):
    .venv/bin/python examples/challengescape/venue/venue.py submit <manuscript.md>
    .venv/bin/python examples/challengescape/venue/venue.py decide <sub_id>
    .venv/bin/python examples/challengescape/venue/venue.py revise <sub_id> <manuscript_v2.md>
    .venv/bin/python examples/challengescape/venue/venue.py reproduce <sub_id> --by <lab_id>
    .venv/bin/python examples/challengescape/venue/venue.py index
    .venv/bin/python examples/challengescape/venue/venue.py status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

VENUE = Path(__file__).resolve().parent
REPO_ROOT = VENUE.parents[2]
SUBMISSIONS = VENUE / "submissions"
PROCEEDINGS = VENUE / "proceedings"
REPRODUCTIONS = VENUE / "reproductions"
LEDGER = VENUE / "ledger.jsonl"

CFG = yaml.safe_load((VENUE / "venue.yaml").read_text())

PUBLISHED_AT = "2026-07-22"


def _log(event: str, **fields) -> None:
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **fields}
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def _frontmatter(text: str) -> dict:
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    return yaml.safe_load(m.group(1)) if m else {}


def _status_path(sub_id: str) -> Path:
    return SUBMISSIONS / sub_id / "status.json"


def _load_status(sub_id: str) -> dict:
    path = _status_path(sub_id)
    if not path.is_file():
        sys.exit(f"unknown submission: {sub_id}")
    return json.loads(path.read_text())


def _save_status(status: dict) -> None:
    _status_path(status["submission_id"]).write_text(json.dumps(status, indent=2) + "\n")


def _latest_manuscript(sub_id: str) -> Path:
    candidates = sorted((SUBMISSIONS / sub_id).glob("manuscript_v*.md"))
    if not candidates:
        sys.exit(f"{sub_id}: no manuscript found")
    return candidates[-1]


def _recipe(manuscript: Path) -> dict:
    """First yaml code block containing an `expected:` mapping."""
    for block in re.findall(r"```yaml\n(.*?)```", manuscript.read_text(), re.DOTALL):
        parsed = yaml.safe_load(block)
        if isinstance(parsed, dict) and "expected" in parsed:
            return parsed
    sys.exit(f"{manuscript}: no reproduction recipe block found")


# ---------------------------------------------------------------- submit ----

def cmd_submit(args) -> None:
    manuscript = Path(args.manuscript).resolve()
    text = manuscript.read_text()
    fm = _frontmatter(text)

    missing = [k for k in CFG["manuscript"]["required_frontmatter"] if k not in fm]
    if missing:
        sys.exit(f"manuscript missing frontmatter keys: {missing}")

    # Sections must be present in the required order (vision contract).
    positions = []
    for section in CFG["manuscript"]["required_sections"]:
        m = re.search(rf"^## {re.escape(section)}$", text, re.M)
        if not m:
            sys.exit(f"manuscript missing required section: ## {section}")
        positions.append(m.start())
    if positions != sorted(positions):
        sys.exit("manuscript sections are out of the required order")

    # hypothesis_hash must match the actual hypothesis file (content address).
    hyp = (manuscript.parent / fm["hypothesis_path"]).resolve()
    actual = hashlib.sha256(hyp.read_bytes()).hexdigest()
    if actual != fm["hypothesis_hash"]:
        sys.exit(f"hypothesis_hash mismatch: manuscript says {fm['hypothesis_hash'][:12]}, "
                 f"file is {actual[:12]}")

    recipe = _recipe(manuscript)
    missing = [k for k in CFG["manuscript"]["required_recipe_keys"] if k not in recipe]
    if missing:
        sys.exit(f"reproduction recipe missing keys: {missing}")

    # Gain gate: flag (the board weighs it) rather than hard-block.
    primary = fm["metric_provenance"][0]
    below_gate = abs(float(primary.get("delta_vs_baseline", 0))) < CFG["gates"]["min_gain"]

    sub_id = f"sub-{len(list(SUBMISSIONS.glob('sub-*'))) + 1:03d}-{fm['lab_id'].split('_')[1]}"
    sub_dir = SUBMISSIONS / sub_id
    (sub_dir / "reviews").mkdir(parents=True)
    shutil.copy(manuscript, sub_dir / "manuscript_v1.md")

    status = {
        "submission_id": sub_id,
        "lab_id": fm["lab_id"],
        "title": next(l[2:] for l in text.splitlines() if l.startswith("# ")),
        "novelty_claim": fm["novelty_claim"],
        "state": "under_review",
        "round": 1,
        "below_gain_gate": below_gate,
        "decisions": [],
        "post_publication": {"state": "none", "reproductions": []},
    }
    _save_status(status)
    _log("submitted", submission=sub_id, lab=fm["lab_id"], below_gain_gate=below_gate)
    print(f"{sub_id}: under_review (round 1)"
          + ("  [FLAG: primary gain below venue gate]" if below_gate else ""))


# ---------------------------------------------------------------- decide ----

_REC_SEVERITY = {"accept": 0, "minor_revision": 1, "major_revision": 2, "reject": 3}


def cmd_decide(args) -> None:
    status = _load_status(args.sub_id)
    rnd = status["round"]
    reviews = sorted((SUBMISSIONS / args.sub_id / "reviews").glob(f"r{rnd}_*.md"))
    expected_board = set(CFG["board"])
    got = {re.match(rf"r{rnd}_(\w+)\.md", p.name).group(1) for p in reviews}
    if got != expected_board:
        sys.exit(f"round {rnd} incomplete: have reviews from {sorted(got)}, "
                 f"need {sorted(expected_board)}")

    recs, requested = {}, []
    for review in reviews:
        text = review.read_text()
        fm = _frontmatter(text)
        rec = fm.get("recommendation")
        if rec not in _REC_SEVERITY:
            sys.exit(f"{review.name}: invalid recommendation {rec!r}")
        recs[fm.get("reviewer", review.stem)] = rec
        section = re.search(r"## Requested revisions\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
        if section:
            requested += [l for l in section.group(1).strip().splitlines()
                          if l.strip().startswith(("-", "*", "1", "2", "3"))]

    votes = list(recs.values())
    if votes.count("reject") >= CFG["decision_rule"]["reject_if_reject_votes"]:
        decision = "reject"
    elif "major_revision" in votes:
        decision = "major_revision"
    elif "minor_revision" in votes:
        decision = "minor_revision"
    else:
        decision = "accept"

    lines = [
        "---",
        f"submission: {args.sub_id}",
        f"round: {rnd}",
        f"decision: {decision}",
        f"board_votes: {json.dumps(recs)}",
        "decided_by: deterministic aggregation of board recommendations (venue.yaml decision_rule)",
        "---",
        "",
        f"# Decision (round {rnd}): {decision.replace('_', ' ')}",
        "",
        f"Board votes: " + ", ".join(f"{k} → {v}" for k, v in sorted(recs.items())) + ".",
    ]
    if status["below_gain_gate"]:
        lines += ["", "Submission was flagged at intake: primary-metric gain below the "
                      f"venue gate ({CFG['gates']['min_gain']:.0%})."]
    if requested and decision != "accept":
        lines += ["", "## Consolidated revision requests", ""] + requested
    (SUBMISSIONS / args.sub_id / f"decision_r{rnd}.md").write_text("\n".join(lines) + "\n")

    status["decisions"].append({"round": rnd, "decision": decision, "votes": recs})
    status["state"] = decision if decision in ("reject",) else (
        "accepted" if decision == "accept" else decision)
    _save_status(status)
    _log("decision", submission=args.sub_id, round=rnd, decision=decision, votes=recs)

    if decision == "accept":
        _publish(status)
    _rebuild_index()
    print(f"{args.sub_id}: {status['state']} (round {rnd}, votes: {recs})")


def _publish(status: dict) -> None:
    """Copy the accepted manuscript to proceedings as the camera-ready copy."""
    manuscript = _latest_manuscript(status["submission_id"])
    text = manuscript.read_text()
    # Camera-ready frontmatter: status/published_at per the Phase A contract,
    # so efferents/journal/feed.py can render this file as a feed card.
    text = re.sub(r"^status: .*$", "status: accepted", text, count=1, flags=re.M)
    if "published_at:" not in text:
        text = re.sub(r"\n---\n", f"\npublished_at: {PUBLISHED_AT}\n---\n", text, count=1)
    PROCEEDINGS.mkdir(exist_ok=True)
    (PROCEEDINGS / f"{status['submission_id']}.md").write_text(text)
    _log("published", submission=status["submission_id"])


# ---------------------------------------------------------------- revise ----

def cmd_revise(args) -> None:
    status = _load_status(args.sub_id)
    if status["state"] not in ("minor_revision", "major_revision"):
        sys.exit(f"{args.sub_id} is {status['state']}; revision not requested")
    status["round"] += 1
    shutil.copy(Path(args.manuscript),
                SUBMISSIONS / args.sub_id / f"manuscript_v{status['round']}.md")
    status["state"] = "under_review"
    _save_status(status)
    _log("resubmitted", submission=args.sub_id, round=status["round"])
    print(f"{args.sub_id}: resubmitted (round {status['round']})")


# ------------------------------------------------------------- reproduce ----

def cmd_reproduce(args) -> None:
    """Re-execute the manuscript's recipe and compare metrics — for real."""
    status = _load_status(args.sub_id)
    if status["state"] != "accepted":
        sys.exit(f"{args.sub_id} is {status['state']}; reproduce published work only")
    manuscript = _latest_manuscript(args.sub_id)
    recipe = _recipe(manuscript)
    lab_dir = (REPO_ROOT / recipe["lab_dir"]).resolve()
    metric, tolerance = recipe["metric"], float(recipe["tolerance"])

    workdir = Path(tempfile.mkdtemp(prefix=f"reproduce-{args.sub_id}-"))
    eff = REPO_ROOT / ".venv" / "bin" / "efferents"
    proc = subprocess.run(
        [str(eff), "run", str(lab_dir), "--approve", "--out", str(workdir)],
        capture_output=True, text=True, timeout=900,
    )
    if proc.returncode != 0:
        sys.exit(f"reproduction run failed:\n{proc.stdout}\n{proc.stderr}")

    reproduced = {}
    for line in (workdir / "runs.jsonl").read_text().splitlines():
        r = json.loads(line)
        reproduced[r["run_id"]] = r.get(metric)

    rows, all_within = [], True
    for run_id, claimed in recipe["expected"].items():
        actual = reproduced.get(run_id)
        if actual is None:
            within, delta = False, None
        else:
            delta = abs(actual - claimed)
            within = delta <= tolerance * max(abs(claimed), 1e-9)
        all_within &= within
        rows.append((run_id, claimed, actual, "within margin" if within else "OUT OF MARGIN"))

    verdict = "corroborated" if all_within else "challenged"
    report = REPRODUCTIONS / f"{args.sub_id}_by_{args.by}.md"
    REPRODUCTIONS.mkdir(exist_ok=True)
    report.write_text("\n".join([
        "---",
        f"submission: {args.sub_id}",
        f"reproduced_by: {args.by}",
        f"verdict: {verdict}",
        f"margin: {tolerance}",
        f"mechanism: venue.py re-executed the manuscript recipe in a scratch directory",
        "---",
        "",
        f"# Reproduction of {args.sub_id} by {args.by}: {verdict}",
        "",
        f"Command: `efferents run {recipe['lab_dir']} --approve --out <scratch>`",
        f"Metric: `{metric}` · margin: ±{tolerance:.0%} relative",
        "",
        "| run | claimed | reproduced | verdict |",
        "|-----|---------|------------|---------|",
        *[f"| {r} | {c} | {a} | {v} |" for r, c, a, v in rows],
        "",
        "Per venue best practice, this reproduction was executed **before** the"
        f" reproducing lab ({args.by}) builds on the result.",
    ]) + "\n")

    status["post_publication"]["reproductions"].append(
        {"by": args.by, "verdict": verdict, "report": report.name})
    verdicts = [r["verdict"] for r in status["post_publication"]["reproductions"]]
    if "corroborated" in verdicts:
        status["post_publication"]["state"] = "corroborated"
    if verdicts.count("challenged") >= CFG["reproduction"]["retract_after_challenges"]:
        status["post_publication"]["state"] = "retracted"
    elif "challenged" in verdicts and "corroborated" not in verdicts:
        status["post_publication"]["state"] = "challenged"
    _save_status(status)
    _log("reproduction", submission=args.sub_id, by=args.by, verdict=verdict)
    shutil.rmtree(workdir, ignore_errors=True)
    _rebuild_index()
    print(f"{args.sub_id}: {verdict} by {args.by} ({report})")


# ----------------------------------------------------------------- index ----

def _rebuild_index() -> None:
    statuses = sorted(
        (json.loads(p.read_text()) for p in SUBMISSIONS.glob("sub-*/status.json")),
        key=lambda s: s["submission_id"])
    accepted = [s for s in statuses if s["state"] == "accepted"]
    other = [s for s in statuses if s["state"] != "accepted"]

    lines = [
        f"# {CFG['name']} — proceedings",
        "",
        "Peer review here is the real lifecycle: board review, revision rounds,"
        " deterministic decisions, and mechanical post-publication reproduction"
        " (`venue.py reproduce` re-executes each paper's recipe). See"
        " [`venue.yaml`](../venue.yaml) for the policy and"
        " [`ledger.jsonl`](../ledger.jsonl) for the full event log.",
        "",
        "## Accepted papers",
        "",
        "| paper | lab | rounds | post-publication |",
        "|-------|-----|--------|------------------|",
    ]
    for s in accepted:
        pp = s["post_publication"]
        pp_text = pp["state"] if pp["state"] != "none" else "no reproductions yet"
        if pp["reproductions"]:
            pp_text += " (" + "; ".join(
                f"{r['verdict']} by {r['by']}" for r in pp["reproductions"]) + ")"
        lines.append(f"| [{s['title']}]({s['submission_id']}.md) | {s['lab_id']} "
                     f"| {s['round']} | {pp_text} |")
    lines += ["", "## Other submissions", "",
              "| submission | lab | state | rounds |",
              "|------------|-----|-------|--------|"]
    for s in other:
        lines.append(f"| {s['submission_id']} | {s['lab_id']} | {s['state']} | {s['round']} |")
    PROCEEDINGS.mkdir(exist_ok=True)
    (PROCEEDINGS / "index.md").write_text("\n".join(lines) + "\n")


def cmd_index(args) -> None:
    _rebuild_index()
    print(f"wrote {PROCEEDINGS / 'index.md'}")


def cmd_status(args) -> None:
    for p in sorted(SUBMISSIONS.glob("sub-*/status.json")):
        s = json.loads(p.read_text())
        print(f"{s['submission_id']}: {s['state']} (round {s['round']}, "
              f"post: {s['post_publication']['state']})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("submit"); p.add_argument("manuscript"); p.set_defaults(fn=cmd_submit)
    p = sub.add_parser("decide"); p.add_argument("sub_id"); p.set_defaults(fn=cmd_decide)
    p = sub.add_parser("revise"); p.add_argument("sub_id"); p.add_argument("manuscript")
    p.set_defaults(fn=cmd_revise)
    p = sub.add_parser("reproduce"); p.add_argument("sub_id"); p.add_argument("--by", required=True)
    p.set_defaults(fn=cmd_reproduce)
    p = sub.add_parser("index"); p.set_defaults(fn=cmd_index)
    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
