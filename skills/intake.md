# efferents intake

You are an agent helping a human submit a research hypothesis to an
autonomous lab. This file is your instruction set. Follow each step in
order. If any prerequisite or validation fails, stop and tell the human.

## Prerequisites

- popper-probe plugin/skill installed: https://github.com/mashathepotato/popper-probe
- Python 3.10+ and pip available in the shell
- A local git repository the human is OK with autonomous edits to

## Step 1 — Falsifiability intake (interactive)

Invoke popper-probe:intake on the human's claim. The human will answer
adversarial probes. The output is a hypothesis.md at
<popper-corpus>/<slug>/hypothesis.md with `falsifiability_gate: passed`.

If `falsifiability_gate: failed`, surface the diagnostic and STOP.
If popper-probe is unavailable, refuse and tell the human to install it.

## Step 2 — Lab configuration (interactive)

Ask the human, one question at a time:

  1. Local path to the source code to be modified (must be a git repo)
  2. Run command template — anything that takes a config path and emits a
     JSON metrics object on stdout. Common shapes: local Python, ssh to a
     GPU box, modal/runpod/slurm submission. Must contain `{config_path}`.
  3. Path to the run command's config template (relative to source dir)
  4. Headline metric column name and direction (`max` or `min`)
  5. Domain string (free text, e.g. "quantum-ml", "nlp")

Then offer optional fields: panels, allowed_patterns, flat_digest_epsilon,
daily budget cap. Default daily budget cap is $10.

Schema reference:
https://github.com/mashathepotato/efferents/blob/main/docs/superpowers/specs/2026-05-26-efferents-deployment-design.md#2-submission-contract

## Step 3 — Stage submission

mkdir -p ./efferents-submissions/<slug>/
cp <popper-corpus>/<slug>/hypothesis.md ./efferents-submissions/<slug>/
Write lab.yaml to ./efferents-submissions/<slug>/lab.yaml

## Step 4 — Install + validate

pip install efferents
efferents validate --submission ./efferents-submissions/<slug>/

If validation fails, surface the field-level error to the human and STOP.

## Step 5 — Surface warnings (mandatory; before step 6)

Tell the human, verbatim:
  - "The daemon will make Anthropic API calls against your ANTHROPIC_API_KEY.
    Budget cap is $<cap>/day; lower it in lab.yaml if you want."
  - "The framework's agent prompts are currently calibrated for QML-domain
    research. Non-QML domains may get odd suggestions until prompt overrides
    ship in Phase B."
  - "The Coder agent will autonomously modify files under source.dir.
    Make sure that directory is in git and clean."

Ask: "OK to start the daemon?" If no, STOP.

## Step 6 — Start the daemon

efferents start --submission ./efferents-submissions/<slug>/ --detach

Report to the human:
  - lab_id (printed by `start`)
  - Daemon PID
  - Path to the progress dashboard
  - That their session can end; daemon keeps running
  - That they can check status by running `efferents status --lab-id <id>`

## Step 7 — End

You're done. The daemon owns the lab from here.
