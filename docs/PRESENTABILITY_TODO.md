# Presentability audit — efferents

Goal: a technical buyer can clone, run **one command**, and understand the
product in 2 minutes. Audit performed 2026-06-25. Severity: 🔴 blocker for a
demo, 🟡 hurts credibility, 🟢 nice-to-have.

## Findings

### Entrypoints / quickstart
- 🔴 **No `python -m efferents` entrypoint.** `efferents/__init__.py` is empty and
  there is no package-level `__main__.py`. `python -m efferents …` fails.
- 🔴 **No API-key-free path to see output.** Every documented run (`efferents start`,
  the `intake.md` trial) boots the Orchestrator, which calls Anthropic. A buyer
  with no `ANTHROPIC_API_KEY` cannot see a single artifact. There is no `demo`
  command.
- 🟡 `pyproject.toml` only exposes `efferents = efferents.cli:main`. Matches the
  CLI, but README never shows a command that works offline.

### README (buyer-facing copy)
- 🔴 First line of status: *"Status: scaffold … not yet runnable as a generic
  framework."* Reads as "do not use." Buys nothing for a cold reader.
- 🟡 Leads with the multi-lab/venue **vision** ("publish papers to a shared
  journal", "efferents.com") instead of the product wedge: **local-first,
  private experiment loops + reviewed internal research memos with provenance.**
- 🟡 Heavy `auto-qml` / QML framing throughout ("quantum-conditioned diffusion",
  "HEP jet data"). Buyer-irrelevant; belongs in DEVELOPMENT/historical notes.
- 🟡 No 60-second quickstart, no example output, no budget/approval/safety
  section, no design-partner positioning.
- 🟡 Uses "papers" / "AI-written papers" framing. Should be "reviewed internal
  research memos" and "lab journal."

### Landing page (`web/landing/`)
- 🟡 Headline "Autonomous research labs that publish papers." + footer "markdown
  is the SDK" — abstract, not the local-first ML wedge.
- 🟡 Copy is built around an agent reading `intake.md` and a shared public
  journal, not a technical buyer pointing it at their own repo.
- 🟡 No "why local-first", no example output, no design-partner CTA, no
  screenshot/placeholder of the actual demo output.

### Repo surface / hygiene
- 🟡 **No LICENSE.** Blocks adoption. (Add a TODO — do not invent a license.)
- 🟡 **No `.env.example`** though `ANTHROPIC_API_KEY` / `submission/.env` are used.
- 🟡 `examples/smoke-lab/README.md` carries a "Caveat" admitting prompts are
  "still calibrated for the QML reference lab." Honest but undercuts confidence;
  reframe as a known limitation in DEVELOPMENT, keep example crisp.
- 🟢 `CLAUDE.md` enumerates QML hardcodes as *open work*; several are now solved
  by `LabConfig` (lab.py). Stale relative to code — fine internally, but should
  not be the buyer's first impression (it is linked from README top).
- 🟢 `docs/templates/qml-lab.py.example` is QML-specific but clearly a labeled
  reference template — acceptable.

### What already works (keep, surface it)
- ✅ `LabConfig` loads a lab from `lab.yaml` + `hypothesis.md` (lab-agnostic).
- ✅ `efferents validate / start / status / stop / list / serve` CLI is real.
- ✅ Read-only dashboard server (`efferents serve`).
- ✅ 247 unit tests pass (3 skipped, integration/slow excluded).
- ✅ `examples/smoke-lab/` is a working non-QML lab with a stub executor.

## Plan (small, working changes — no architecture rewrite)

1. ✅ Add `efferents/__main__.py` → delegates to `cli.main`.
2. ✅ Add `efferents demo <lab>` (and `python -m efferents demo <lab>`): runs a
   bounded, **deterministic, no-API** experiment loop on the smoke lab and emits
   `journal/00x_*.md`, `runs.jsonl`, `claims.jsonl`, `dashboard.html`.
3. ✅ Add `examples/repo-adapter/efferents.yaml` (point-at-your-repo config) +
   minimal loader.
4. ✅ Make provenance visible: reviewed memo has all sections + an evidence table
   keyed by run_id / metric / source_path.
5. ✅ Rewrite README top for buyers; move scaffold/QML/architecture notes to
   `DEVELOPMENT.md`.
6. ✅ Rework landing page for the local-first wedge + example output + pilot CTA.
7. ✅ Add `.env.example`, `LICENSE` (Apache-2.0), gitignore demo output.
