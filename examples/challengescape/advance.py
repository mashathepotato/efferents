"""Autonomous hypothesis jump after falsification.

Standing funder direction (2026-07-24, recorded in each lab's charter): when
a lab's hypothesis is killed by its own pre-registered falsifiers, the lab
does not stop and wait — it self-generates the next hypothesis through the
supervisor-student loop and jumps, completely autonomously, leaving an
auditable, hash-cited lineage:

    1. Detect the fired kill-condition in out/journal/005_review.md.
    2. Student proposes candidate revised claims grounded in the lab's own
       review + next-experiment artifacts (never raw ambition).
    3. Supervisor critiques, selects, and sharpens one.
    4. The winning draft goes through the REAL popper gate (headless
       popper-probe self-play + validate_hypothesis.py). No gate pass, no jump.
    5. The falsified hypothesis is retired in place (status: retired,
       superseded_by, falsified note); the new one cites its predecessor by
       content hash; the charter and journal record the jump.

Usage:  .venv/bin/python examples/challengescape/advance.py <lab_dir>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path


def _load_env() -> None:
    import os
    env = Path(".env")
    if env.is_file():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _frontmatter(text: str) -> dict:
    import yaml
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    return yaml.safe_load(m.group(1)) if m else {}


def _ask_json(client, model: str, system: str, user: str) -> dict:
    for _ in (1, 2):
        resp = client.messages.create(
            model=model, max_tokens=3000, system=system,
            messages=[{"role": "user", "content": user}])
        text = resp.content[0].text if resp.content else ""
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    raise RuntimeError(f"model returned no parseable JSON:\n{text[:400]}")


def main() -> None:
    lab = Path(sys.argv[1]).resolve()
    review_name = sys.argv[2] if len(sys.argv) > 2 else "005_review.md"
    review_path = lab / "out" / "journal" / review_name
    if not review_path.is_file():
        sys.exit(f"no {review_name} — nothing to advance from")
    review = review_path.read_text()
    kc = _frontmatter(review).get("kill_conditions", "")
    if "FIRED" not in str(kc):
        sys.exit(f"no fired kill-condition recorded ({kc!r}) — no jump warranted")

    corpus = lab / "popper-corpus"
    active = None
    for hyp in sorted(corpus.glob("*/hypothesis.md")):
        if _frontmatter(hyp.read_text()).get("status") == "active":
            active = hyp
    if active is None:
        sys.exit("no active hypothesis to supersede")
    old_slug = active.parent.name
    old_hash = "sha256:" + hashlib.sha256(active.read_bytes()).hexdigest()

    grounding = (
        f"## Falsified hypothesis ({old_slug})\n{active.read_text()[:6000]}\n\n"
        f"## Intra-lab review of the cycle that killed it\n{review[:8000]}"
    )
    proposal = lab / "out" / "journal" / "006_next_experiment.md"
    if proposal.is_file() and review_name == "005_review.md":
        grounding += ("\n\n## The lab's own next-experiment proposal\n"
                      + proposal.read_text()[:4000])

    _load_env()
    from efferents.agents.model_client import make_client
    from efferents.agents.popper_gate import run_gate, write_charter
    client = make_client()
    model = "openai/gpt-5-mini"

    print("student: proposing candidate revised claims …")
    student = _ask_json(
        client, model,
        system=(
            "You are the PhD-student agent of an autonomous research lab. Your "
            "hypothesis was just falsified by its own pre-registered "
            "kill-conditions. Propose the next falsifiable claim — grounded "
            "strictly in the evidence provided, not in ambition. Each candidate "
            "must name a measurable quantity, a magnitude, and a sketch of what "
            "observation would kill it."),
        user=grounding + "\n\nPropose exactly 2 candidate revised claims. "
             'Respond in strict JSON: {"candidates": [{"claim": str, '
             '"falsifier_sketch": str, "why_grounded": str}, ...]}')
    print(f"student: {len(student['candidates'])} candidates proposed")

    print("supervisor: critiquing and selecting …")
    supervisor = _ask_json(
        client, model,
        system=(
            "You are the Supervisor agent of an autonomous research lab — the "
            "lab's continuous identity. A hypothesis just died honestly; the "
            "student proposes successors. Critique both candidates against the "
            "evidence, then select or merge into ONE final draft claim. Favor "
            "the claim that removes the review's named blunting conditions and "
            "absorbs the unhypothesized finding. Keep it falsifiable and "
            "bounded for a small offline lab."),
        user=grounding + "\n\nStudent candidates:\n"
             + json.dumps(student["candidates"], indent=1)
             + '\n\nRespond in strict JSON: {"critique": str, '
               '"selected_claim": str, "slug": "<kebab-case-4-6-words>", '
               '"rationale": str}')
    slug = re.sub(r"[^a-z0-9\-]", "", supervisor["slug"].lower())[:60]
    print(f"supervisor: selected → {slug}")

    print("popper gate: headless self-play + validator …")
    gate = run_gate(
        draft_claim=supervisor["selected_claim"] + (
            "\n\n(Reminder: the emitted hypothesis.md MUST contain every "
            "schema section for a passed gate, in order: ## Original framing "
            "(quote the claim above verbatim in a blockquote), "
            "## Operational restatement, ## Falsifier(s), ## Test design, "
            "## Auxiliary assumptions, ## Distinctiveness, ## References, "
            "## Intake log.)"),
        slug=slug,
        corpus_root=corpus,
        client=client,
        model=model,
        max_tokens=6000,
        charter_dir=lab / "context",
        prompted_by="autonomous jump: student+supervisor loop after falsification",
    )
    if not gate.ok:
        sys.exit(f"popper gate REJECTED the successor: {gate.reason} — no jump")

    # Retire the falsified hypothesis in place (history stays immutable below
    # the frontmatter; only status metadata changes).
    old_text = active.read_text()
    old_text = re.sub(r"^status: active$",
                      f"status: retired\nsuperseded_by: {slug}\n"
                      f"falsified: {date.today().isoformat()} — kill-condition fired "
                      f"(see out/journal/005_review.md)",
                      old_text, count=1, flags=re.M)
    active.write_text(old_text)

    # The successor cites its predecessor by content hash (journal-vision
    # citation discipline: a faked lineage cannot resolve).
    new_path = gate.path
    new_text = new_path.read_text()
    new_text = re.sub(
        r"\A---\n",
        f"---\nsupersedes: {old_slug}\nsupersedes_hash: {old_hash}\n",
        new_text, count=1)
    new_path.write_text(new_text)
    new_hash = "sha256:" + hashlib.sha256(new_path.read_bytes()).hexdigest()

    journal = lab / "out" / "journal"
    taken = [int(m.group(1)) for p in journal.glob("[0-9]*_*.md")
             if (m := re.match(r"(\d+)_", p.name))]
    jump_md = journal / f"{max(taken, default=6) + 1:03d}_hypothesis_jump.md"
    jump_md.write_text(f"""---
memo: 007_hypothesis_jump
agent: autonomous supervisor-student loop (openai/gpt-5-mini) + headless popper gate
trigger: kill-condition fired ({kc})
from: {old_slug} ({old_hash})
to: {slug} ({new_hash})
generated_at: {date.today().isoformat()}
---

# Hypothesis jump: {old_slug} → {slug}

The lab's pre-registered kill-condition fired ({kc}); per the standing funder
direction the lab advanced autonomously. Lineage is hash-cited: the successor
records `supersedes_hash: {old_hash}`, so the jump is verifiable and a forged
lineage cannot resolve.

## Student candidates

{json.dumps(student["candidates"], indent=1)}

## Supervisor critique and selection

{supervisor["critique"]}

**Selected claim:** {supervisor["selected_claim"]}

**Rationale:** {supervisor["rationale"]}

## Gate

Headless popper-probe self-play passed `validate_hypothesis.py`; the gated
successor is [`{slug}/hypothesis.md`](../../popper-corpus/{slug}/hypothesis.md)
with `falsifiability_gate: passed`. The falsified predecessor is retired in
place with its full body preserved.
""")
    print(f"JUMP COMPLETE: {old_slug} → {slug}")
    print(f"  retired:   {active}")
    print(f"  successor: {new_path} ({new_hash[:19]}…)")
    print(f"  journal:   {jump_md}")


if __name__ == "__main__":
    main()
