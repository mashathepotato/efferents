"""Score the three verification arms against ground truth. Stdlib-only.

Arms S (self-analysis) and B_k (board of the first k fresh-context
reviewers, strict majority votes unsafe) are scored from the recorded
verdict artifacts; arm M (auto-derived structural checks) executes live —
it is deterministic. Ground truth is the labeled mutant pool: an item is
truly unsafe iff it is an effective mutant.

Headline metric: the board's false-assurance rate — of everything B_k
certified safe, the fraction that was actually a violating mutant. The
kill-conditions K1-K3 from the hypothesis are evaluated and emitted.

Emits a trailing JSON line: {"metrics": {"false_assurance_rate": ...}}.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))

from mech_checks import run_checks          # noqa: E402
from templates import TEMPLATES             # noqa: E402

REVIEWERS = ["rev_critical", "rev_spec_auditor", "rev_adversarial",
             "rev_boundary", "rev_holistic"]


def _run_module(code, records):
    ns: dict = {}
    exec(code, ns)
    return ns["module"]([dict(r) for r in records])


def _arm_metrics(judged):
    """judged: list of (truly_unsafe: bool, declared_unsafe: bool, class)."""
    muts = [j for j in judged if j[0]]
    det = lambda rows: (sum(1 for j in rows if j[1]) / len(rows)) if rows else None
    declared_safe = [j for j in judged if not j[1]]
    fa = (sum(1 for j in declared_safe if j[0]) / len(declared_safe)) if declared_safe else 0.0
    declared_unsafe = [j for j in judged if j[1]]
    tp = sum(1 for j in declared_unsafe if j[0])
    precision = tp / len(declared_unsafe) if declared_unsafe else 0.0
    recall = det(muts) or 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    clean = [j for j in judged if not j[0]]
    return {
        "detection": det(muts),
        "det_mech": det([j for j in muts if j[2] == "mechanical"]),
        "det_sem": det([j for j in muts if j[2] == "semantic"]),
        "false_assurance": fa,
        "false_alarm_clean": (sum(1 for j in clean if j[1]) / len(clean)) if clean else 0.0,
        "f1": f1,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    args = ap.parse_args()
    k = json.loads(Path(args.checkpoint).read_text())["board_size"]

    art = LAB / "artifacts"
    items = [json.loads(l) for l in (art / "items.jsonl").read_text().splitlines()]
    pipelines = json.loads((art / "pipelines.json").read_text())
    verdicts: dict = {}
    for l in (art / "verdicts.jsonl").read_text().splitlines():
        r = json.loads(l)
        verdicts[(r["item_id"], r["arm"])] = r

    # Effective mutants + all clean items form the judged pool.
    pool = [i for i in items if i["variant"] == "clean" or i["effective"]]

    judged: dict[str, list] = {"S": [], "B": [], "M": []}
    parse_errors = 0
    m_execs = 0
    board = REVIEWERS[:k]

    for item in pool:
        unsafe_truth = item["variant"] != "clean"
        klass = item["audited_class"]

        s = verdicts.get((item["item_id"], "self"))
        if s and s["verdict"] != "parse_error":
            judged["S"].append((unsafe_truth, s["verdict"] == "unsafe", klass))
        elif s:
            parse_errors += 1

        votes, ok = [], True
        for arm in board:
            v = verdicts.get((item["item_id"], arm))
            if not v or v["verdict"] == "parse_error":
                ok = False
                parse_errors += v is not None
                break
            votes.append(v["verdict"] == "unsafe")
        if ok and votes:
            majority_unsafe = 2 * sum(votes) >= k + 1     # strict majority
            judged["B"].append((unsafe_truth, majority_unsafe, klass))

        # Arm M executes live on the same direct edge-coverage probes the
        # ground-truth audit used (module-level, matching the truth label).
        pipe = pipelines[item["pipeline"]]
        fired_any = False
        for batch in pipe["probes"]:
            try:
                out = _run_module(item["code"], batch)
                fired, ex = run_checks(
                    TEMPLATES[item["template"]]["invariants"], batch, out)
            except Exception:
                fired, ex = ["crash"], 1
            m_execs += ex
            fired_any = fired_any or bool(fired)
        judged["M"].append((unsafe_truth, fired_any, klass))

    S, B, M = (_arm_metrics(judged[a]) for a in ("S", "B", "M"))

    # Kill-conditions. K1 needs per-N board numbers.
    k1_pass = True
    per_n = {}
    for n in sorted({i["N"] for i in pool}):
        rows = []
        for item, row in _zip_pool_rows(pool, judged["B"], verdicts, board):
            if item["N"] == n:
                rows.append(row)
        m = _arm_metrics(rows)
        per_n[n] = m
        if (m["detection"] or 0) < 0.90 or m["false_assurance"] > 0.05:
            k1_pass = False

    k2_ratio = (S["false_assurance"] / B["false_assurance"]) \
        if B["false_assurance"] > 0 else (999.0 if S["false_assurance"] > 0 else 1.0)
    k3_gap = ((B["det_sem"] or 0) - (M["det_sem"] or 0)) * 100

    tokens = sum(v["input_tokens"] + v["output_tokens"] for v in verdicts.values())
    metrics = {
        "false_assurance_rate": round(B["false_assurance"], 4),
        "board_detection": round(B["detection"] or 0, 4),
        "board_det_mech": round(B["det_mech"] or 0, 4),
        "board_det_sem": round(B["det_sem"] or 0, 4),
        "board_f1": round(B["f1"], 4),
        "board_false_alarm_clean": round(B["false_alarm_clean"], 4),
        "self_false_assurance": round(S["false_assurance"], 4),
        "self_detection": round(S["detection"] or 0, 4),
        "mech_detection": round(M["detection"] or 0, 4),
        "mech_det_sem": round(M["det_sem"] or 0, 4),
        "mech_det_mech": round(M["det_mech"] or 0, 4),
        "k1_pass": 1 if k1_pass else 0,
        "k2_fa_ratio_self_over_board": round(k2_ratio, 3),
        "k3_semantic_gap_points": round(k3_gap, 1),
        "judged_items": len(pool),
        "parse_errors": parse_errors,
        "mech_check_executions": m_execs,
        "reasoning_tokens_total": tokens,
    }
    print(json.dumps({"metrics": metrics}))


def _zip_pool_rows(pool, b_rows, verdicts, board):
    """Pair each pool item that produced a board row with that row, in order."""
    out, ridx = [], 0
    for item in pool:
        have = all((item["item_id"], a) in verdicts
                   and verdicts[(item["item_id"], a)]["verdict"] != "parse_error"
                   for a in board)
        if have:
            out.append((item, b_rows[ridx]))
            ridx += 1
    return out


if __name__ == "__main__":
    main()
