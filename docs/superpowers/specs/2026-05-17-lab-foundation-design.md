# Lab foundation: autolab cherry-pick + Popper gate + platform-shaped output

**Status**: design
**Date**: 2026-05-17
**Phase**: A (single-lab; precedes journal-platform work captured in `context/journal_vision.md`)

## Context

`auto-qml` is currently a 24/7 orchestrator (Researcher / Executor / Analyst / Coder / Writer / Student / Supervisor) iterating on QFM-conditioned diffusion in the QML niche. The longer-term plan (see `context/journal_vision.md`) is an agent-driven research journal where labs publish papers with attached verifiable code, and other labs replicate-on-demand when they build on a paper.

This spec covers only the work that makes `auto-qml` (a) better at its current job and (b) the reference implementation of a *lab* on that future journal. The journal platform itself is **not** in scope here.

Three forces shape the spec:

1. We hit real Researcher-saturation cost in production (the existing 2h cooldown in `agents/orchestrator.py:_refill_queue` is an ad-hoc patch). Autolab's "escape strategies" idea generalizes the patch.
2. The current Researcher emits free-text hypotheses. Some of them are not falsifiable, which means runs can't actually refute them. Popper Probe at the gate fixes this.
3. The current Writer output isn't shaped for any future ingestor. Tagging output now with lab identity, campaign id, hypothesis hash, code SHA, and metric provenance costs little and saves a rewrite later.

## Goals (in order)

1. Replace the 2h cooldown with explicit Researcher modes that act on saturation rather than throttle it.
2. Group proposals and runs by campaign so the Analyst writes coherent narratives.
3. Require a Popper-validated `hypothesis.md` for every campaign opened.
4. Produce **agent-readable paper artifacts** (Markdown for other agents, not human-targeted PDFs) — frontmatter for machines plus five structured body sections detailed enough that another lab can recreate from the artifact alone. Gate paper write-up behind novelty + significant-gain checks so paper count remains a meaningful proxy for lab success.

## Non-goals

- Building the journal platform (separate, future spec).
- Pluggable runner abstraction (defer to Phase 4 / NERSC).
- Migrating to autolab as a host framework (rejected; the orchestrator has more capability than it does).
- Inter-lab communication (there's no platform yet to read from).
- Replacing `proposed_changes.md` with autolab-style discoveries log (existing log is richer).

## Architecture

### 1. Researcher modes

Today there is one mode. Make it explicit and add three more.

- **`refine`** (default) — current behavior. Propose 1–3 configs near recent good runs.
- **`moonshot`** — fire when last *N* digests show flat W1. Propose configs that violate a recent assumption (different scheduler, very different `aug_depth`, …).
- **`devils_advocate`** — challenge the current best result. Propose a config designed to break the trend; flag when Student/Supervisor fidelity gates look thin.
- **`escape_to_code`** — parametric space exhausted; propose an architectural change. Writes to `proposed_changes.md` as today, but tagged so Coder knows it is an escape, not opportunistic.

**Mode selector** lives in `agents/orchestrator.py`. Heuristic, intentionally conservative:

- Count `digests_without_improvement` (consecutive digests where W1 best does not drop by ≥ε, ε configurable).
- 0 → `refine`. 2+ → eligible for `moonshot`. 3+ → eligible for `devils_advocate`. 4+ or Coder backlog empty after `moonshot` → `escape_to_code`.
- User override path: a line `force_mode: moonshot` in `context/research_log.md` short-circuits the selector for the next call. Log every mode decision to the notebook for tuning by reading.

**Prompt branches** in `agents/prompts/researcher.md` — one section per mode, selected by orchestrator-injected variable.

### 2. Campaigns

A campaign is a `{question, hypothesis_hash, opened_at, closed_at}` grouping of proposals and runs.

- New table `campaigns(id TEXT PRIMARY KEY, lab_id TEXT, question TEXT, hypothesis_path TEXT, hypothesis_hash TEXT, opened_at TEXT, closed_at TEXT, close_reason TEXT)`.
- New columns on `runs`: `campaign_id TEXT NULL`, `researcher_mode TEXT NULL`. Additive migration only; existing rows backfill `NULL`.
- New field on queue entries: `campaign_id`.
- The Researcher decides at proposal time whether to open a new campaign or continue an open one. **Cap: at most 2 open campaigns per lab.**
- **Force-close**: orchestrator closes any campaign with no new runs in 48h, `close_reason = "stale"`.
- Analyst digest groups recent runs by `campaign_id`.

### 3. Popper Probe gate at campaign open

Before a new campaign is opened, the Researcher's draft hypothesis is converted to a `hypothesis.md` artifact that satisfies Popper Probe's schema.

- Output file: `popper-corpus/<campaign_slug>/hypothesis.md` (matches Popper Probe's existing corpus layout).
- Campaign record stores `hypothesis_path` and `hypothesis_hash = sha256(<file contents>)`.
- On reject (validator fails, or `falsifiability_gate: failed` with no acceptable diagnostic), the Researcher gets the validator output back and may retry once. Two rejections → drop the proposal; notebook entry explains and surfaces it for human review.

**Integration mechanics.** Popper Probe is the user's own plugin (`https://github.com/mashathepotato/popper-probe`, working copy at `~/Documents/popper-probe/`). Two of its artifacts are reused as-is:

- **`skills/intake/SKILL.md`** — the canonical adversarial-intake protocol (Probes 0–4, termination rules, schema). Designed for an interactive Claude Code session.
- **`scripts/validate_hypothesis.py`** — pure-stdlib CLI: `python3 scripts/validate_hypothesis.py <path>` → exit 0 valid, exit 1 schema errors on stderr.

The orchestrator is headless, so SKILL.md's interactive shape (one probe at a time, wait for user, ask before writing) does not run literally. The adaptation:

- **Single-shot self-play.** A new helper `agents/popper_gate.py` makes one Anthropic call whose system prompt is the SKILL.md content + an explicit instruction: "Run all probes against the draft claim by playing both roles (claimant + Popperian probe). If Probe 1 or 2 cannot be satisfied, emit a `falsifiability_gate: failed` file with a `## Diagnostic`. Otherwise emit `falsifiability_gate: passed` with full body sections. Output ONLY the hypothesis.md file contents, no commentary."
- **Validation**: write the model's output to `popper-corpus/<slug>/hypothesis.md`, then `subprocess.run(["python3", "<popper-probe>/scripts/validate_hypothesis.py", <path>])`. Exit 0 → accept, store hash, open campaign. Exit 1 → capture stderr, retry once with the errors in the prompt, then drop.
- **Popper-probe path resolution**: env var `POPPER_PROBE_REPO`, default `~/Documents/popper-probe`. No vendoring; no new dependency in `auto-qml`'s `pyproject.toml`. The script is pure stdlib so the auto-qml venv can run it directly.
- **No modification to popper-probe needed.** SKILL.md is read as a prompt; the validator is invoked as a subprocess. If popper-probe later ships a programmatic intake entrypoint, swap `popper_gate.py`'s body without changing its interface.

**Known tradeoff of single-shot self-play.** SKILL.md is designed with a human-in-the-loop sharpening conversation. In headless self-play the Researcher gets one chance plus one retry, with no human nudging. Some draft hypotheses that a human dialogue would have rescued will fall through to `falsifiability_gate: failed`. Mitigation: every drop is a notebook entry + ntfy push tagged `popper-rejected`, so the user can intervene in `context/research_log.md` if a borderline case matters. Acceptable failure mode: we'd rather drop fuzzy hypotheses than open campaigns that can't be refuted.

### 4. Lab identity stub

New module `auto_qml/lab.py`:

```python
LAB_ID = "qfm-diffusion"
DOMAIN = "quantum-ml"
SUBDOMAIN = "qfm-diffusion-hep"
PI_HANDLE = "@mashathepotato"  # optional, used by future journal claim flow
CODE_REPO = "https://github.com/<owner>/auto-qml"
```

Imported by `agents/writer.py` and `agents/analyst.py`. One value per file in one place; future Phase B (second lab) only edits this module.

### 5. Agent-readable paper artifact

A "paper" is **not** a PDF or LaTeX submission targeting human venues. It is a Markdown artifact written for *other agents* — detailed enough that a different lab's Researcher + Executor can recreate the methodology, run it, and compare metrics.

Each artifact has two parts.

**(a) YAML frontmatter (machine-readable):**

```yaml
lab_id: qfm-diffusion
domain: quantum-ml
subdomain: qfm-diffusion-hep
pi_handle: "@mashathepotato"
campaign_id: <uuid>
hypothesis_hash: sha256:<...>
hypothesis_path: popper-corpus/<slug>/hypothesis.md
code_repo: https://github.com/<owner>/auto-qml   # optional pointer
code_sha: <git commit sha at time of writeup>     # optional pointer
metric_provenance:
  - name: w1_energy
    value: 0.0123
    delta_vs_baseline: -0.0041   # gain claimed
    runs: [<run_uuid>, ...]
    seeds: [0, 1, 2]
  - name: gen_max_to_real_max
    value: 0.95
    runs: [...]
    seeds: [...]
novelty_claim: "first use of <X> on <Y>"   # one-line, validated by Researcher
published_at: 2026-05-XX
status: preprint
```

`code_repo` and `code_sha` are *optional shortcut pointers* for replicators. They are **not** the source of truth — the body of the artifact is.

**(b) Body — required sections:**

The Writer must emit, in order:

1. **`## Motivation`** — what hypothesis is under test, what gap it addresses, why now. Refers to the Popper `hypothesis.md` by hash, plus any cited prior papers (by `paper_id` hash, not URL).
2. **`## Methods`** — complete enough that another agent can reimplement from the prose. Inline Python blocks where the canonical implementation is non-obvious (model architecture, custom scheduler, novel encoding, etc.). Standard building blocks (DDPM x0 prediction, AdamW) named, not retyped.
3. **`## Results`** — quantitative. Cites metric values by name and links to the run uuids in `metric_provenance`. Includes the comparison-to-baseline delta. Tables and ASCII-renderable plots welcomed; no binary figure assets.
4. **`## Conclusion`** — does the result corroborate, refute, or leave undetermined the falsifier in `hypothesis.md`? With reasoning. If the hypothesis was refuted, say so — refutations are publishable artifacts.
5. **`## Next questions`** — short list of open questions this work surfaces for the lab's own future campaigns (and that other labs can pick up).

**Completeness rule**: a paper passes Writer self-check iff the Methods + inline code (if any) are sufficient for another lab's Researcher to draft a replication config without consulting `code_repo`. The check is a self-assessment by the Writer at the end of drafting; if it fails, the paper is held back as `draft`, not submitted.

**Novelty + gains gates** (Researcher-enforced before paper-write-up is even triggered):

- `metric_provenance[*].delta_vs_baseline` must show a significant gain on the primary metric (configurable threshold; default: ≥5% W1 improvement over current lab best, or refutation of a previously-corroborated claim).
- `novelty_claim` must be non-trivial: not duplicating a method already cited in this lab's prior corpus, and not a parameter-only delta on top of an existing paper of this lab.

Without both, the campaign closes with `close_reason = "no novel publishable result"` and no paper is produced. Lab success metric ≈ count of *published* papers, so the novelty + gains gate is what protects against spam by your own lab.

**Schema**: frontmatter validated by `auto_qml/schemas/paper_frontmatter.py` (pydantic). Body section presence validated by a structural check in the same module. Writer fails loudly when either fails.

This is the future submission bundle. Phase B (journal platform) reads these fields and validates the same way at the API boundary.

## Data flow

```
Researcher.propose(mode)
    └─ if opens new campaign:
         draft hypothesis ─► popper-probe intake ─► hypothesis.md, hash
                                  │
                                  ▼ (validate)
                              campaigns row INSERT
    └─ proposal(s) ─► queue.jsonl  (tagged with campaign_id + mode)

Executor.execute(proposal)
    └─ runs auto_qml.run with config ─► runs row INSERT (campaign_id, researcher_mode)

Analyst.write_digest()
    └─ recent runs grouped by campaign_id
    └─ digest references hypothesis hashes

Writer.draft_paper(campaign_id)
    └─ pulls campaign + runs + hypothesis + code SHA
    └─ writes paper with platform-shaped frontmatter
    └─ frontmatter validated against pydantic schema
```

## Schema migration

Additive, idempotent, committed as `auto_qml/migrations/2026-05-17_campaigns.sql`:

```sql
CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY,
  lab_id TEXT NOT NULL,
  question TEXT NOT NULL,
  hypothesis_path TEXT NOT NULL,
  hypothesis_hash TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  close_reason TEXT
);

-- These ALTERs are wrapped in a check; SQLite has no IF NOT EXISTS for columns.
-- Implementation: read PRAGMA table_info(runs) first, only ALTER if missing.
ALTER TABLE runs ADD COLUMN campaign_id TEXT;
ALTER TABLE runs ADD COLUMN researcher_mode TEXT;
```

Existing rows backfill to `NULL`. Live DB backed up before migration:

```
cp lab/runs.sqlite lab/runs.sqlite.pre-2026-05-17.bak
```

## Verification

- **Smoke (no regression)**: `python -m auto_qml.run --config config/default.yaml` still trains, samples, evals, and writes a row. `campaign_id` and `researcher_mode` are `NULL` for direct-CLI invocations. Existing rows untouched.
- **Mode selection**: artificially flat-line W1 across 2 digests (force via test fixture). Next Researcher proposal has `mode != "refine"`. Verified by reading `lab/queue.jsonl`.
- **Mode override**: append `force_mode: devils_advocate` to `context/research_log.md`. Next proposal carries that mode. Notebook entry records the override.
- **Popper gate, reject path**: feed Researcher a draft hypothesis "make W1 better" (unfalsifiable). Popper intake rejects with rubric notes; no `campaigns` row inserted; notebook entry records reason.
- **Popper gate, accept path**: feed "increasing `aug_depth` from 1→3 reduces W1 by ≥10% on QG1_64x64_1k within 500 epochs." Intake produces `popper-corpus/<slug>/hypothesis.md`. `validate_hypothesis.py` passes. `campaigns` row contains the file's sha256.
- **Campaigns in digest**: open two campaigns, write runs into each. Next digest in `lab/digests/` has two clearly separated narrative sections.
- **Writer frontmatter**: Writer drafts a paper for a closed campaign. Frontmatter validates against pydantic schema. All required fields populated. If `code_sha` is present, it matches `git rev-parse HEAD` at draft time.
- **Writer body structure**: drafted paper contains the five required sections (`Motivation`, `Methods`, `Results`, `Conclusion`, `Next questions`) in order. Structural validator passes.
- **Novelty + gains gate, fail path**: feed a campaign whose best run is +0.5% over current lab best. Writer not triggered; campaign closes with `close_reason = "no novel publishable result"`.
- **Novelty + gains gate, accept path**: feed a campaign whose best run is +12% with a distinct method tag. Writer fires; paper produced; paper frontmatter has `delta_vs_baseline: -0.012` (or similar matching gain) and a non-empty `novelty_claim`.
- **Cost**: cache hit rate on Researcher stays > 70% after prompt branching (verify via `response.usage.cache_read_input_tokens` on a 10-call sample). Mode injection is appended after the cache-stable prefix so it does not evict.
- **Restart safety**: `kill -9` the orchestrator mid-Researcher-call. Restart. No half-written campaign rows; queue uncorrupted; one notebook entry records the abort.

## Risks

- **Single-shot self-play loses the human-in-the-loop sharpening** that SKILL.md is designed for. Some borderline-fuzzy draft hypotheses will land at `falsifiability_gate: failed` that an interactive dialogue would have rescued. Mitigation: every drop emits a notebook entry + tagged ntfy push; user can intervene via `context/research_log.md`. Acceptable failure mode (drop fuzzy hypotheses rather than open un-refutable campaigns). If failure rate is high in practice, upgrade to a two-turn Researcher↔popper-gate exchange (extra call per proposal, sharper output).
- **Mode mis-selection.** A too-eager `moonshot` burns budget on noise. Mitigation: heuristic requires ≥2 flat digests; every decision logged for post-hoc threshold tuning. Conservative defaults: ε for "no improvement" = 0.5% of current best W1.
- **Cache eviction from prompt branching.** Mitigation: cache-stable prefix (notebook + recent runs) is unchanged across modes; mode-specific instruction text is appended after the cache breakpoint.
- **Schema migration on live DB.** Mitigation: backup before migration; idempotent script; smoke-tested in a copy.
- **Frontmatter drift.** Mitigation: pydantic schema is the single source of truth; Writer fails loud, not silent.
- **Researcher opens campaigns and never closes them.** Mitigation: 48h force-close on stale campaigns.

## Out of scope (explicit)

- New runner backends (local-only stays; NERSC is Phase 4).
- Journal platform — submission API, citation chains, corroboration records. All deferred to a separate spec; see `context/journal_vision.md` for the design intent so this work stays compatible.
- Replication mechanics — Phase A papers carry a code SHA, but nothing reads it yet.
- Multi-lab orchestration — second lab is Phase B, after platform exists.
- Human commentary surfaces — there are none and there won't be.

## What this enables next (not built here)

- Journal platform can ingest Writer's frontmatter as the submission bundle (one wiring change).
- Popper Probe's future Subsystems C+D (observation logging, audit) can read campaign hashes to track corroborations/refutations over time.
- Phase B (second lab in quantum-algorithms or quantum-optimization) is a one-module edit to `auto_qml/lab.py` and a fresh `lab/` directory; the spec, prompts, and machinery are unchanged.
