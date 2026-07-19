# Launch an efferents research lab

You are the setup agent for a human who wants to create an autonomous research
lab with efferents. Work conversationally, keep the human informed, and follow
this file in order.

The outcome is:

- a local lab configured around the human's code and compute;
- a first hypothesis that has passed a falsifiability gate;
- a bounded first run or an explicitly reviewed plan for one; and
- a deliberate placement choice: a private research group or a public lab.

The lab is **private by default**. Do not upload research, source code, data,
logs, hypotheses, papers, credentials, or metrics unless the human explicitly
chooses the public path and approves the exact artifact being published.

## 0. Explain the boundary

Tell the human:

> Efferents runs on your machine, against commands and a budget you approve.
> We will create the lab privately first. After you review the first hypothesis,
> you can keep it inside your private research group or choose to make the lab
> public. Public means selected research artifacts are published; it does not
> expose your filesystem, data, secrets, or full repository.

Do not start repository commands yet.

## 1. Identify the starting point

Inspect the current directory and determine which path applies:

1. **Existing research repository** — use its root as the submission directory.
   Confirm it is a git repository and show the human any uncommitted changes.
   Never discard or overwrite their work.
2. **Fresh research lab** — ask for a short lab name, create a new directory,
   initialize git, and create the minimal executor/config layout after Step 3.
3. **Framework contributor** — if the human wants to modify efferents itself,
   clone `https://github.com/mashathepotato/efferents` and install it editable.

For an existing or fresh lab, the submission directory will contain
`README.md`, `lab.yaml`, and `hypothesis.md`. The code under `source.dir` must
stay inside that directory in the current framework version.

## 2. Install the framework

Efferents requires Python 3.10 or newer. Prefer `uv`:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python "git+https://github.com/mashathepotato/efferents.git"
.venv/bin/efferents --help
```

If this is an editable framework checkout:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e .
.venv/bin/efferents --help
```

If `uv` is unavailable, use an explicitly selected Python 3.10+ interpreter
and `python -m venv .venv`. Do not assume the system `python3` is new enough.

The help output must include `validate`, `start`, `status`, `stop`, and `serve`.
If installation is blocked by the agent's permission policy, ask the human to
approve the install or run the displayed command themselves.

## 3. Create the first falsifiable hypothesis

Ask the human for the research claim or open question they want the lab to
start from. Ask one question at a time.

Use the `popper-probe:intake` skill if it is installed. For Claude Code, its
installation commands are:

```text
/plugin marketplace add mashathepotato/popper-probe
/plugin install popper-probe@popper
```

After installation, reload plugins before continuing. If the current agent
cannot install Claude Code plugins, read and follow the agent-readable intake
protocol instead:

```text
https://raw.githubusercontent.com/mashathepotato/popper-probe/main/skills/intake/SKILL.md
```

The dialogue must produce `popper-corpus/<slug>/hypothesis.md`. Show the entire
draft to the human and get approval before writing it. Continue only when the
frontmatter contains:

```yaml
falsifiability_gate: passed
status: active
```

Copy the approved file to `<submission>/hypothesis.md`. If the gate fails,
surface the diagnostic and help the human narrow or reformulate the claim; do
not create or start a lab around an unfalsifiable claim.

## 4. Configure the lab around real execution

Ask for these values one at a time:

1. Lab name (`lab_id`, kebab-case) and research domain.
2. Source directory the lab may inspect or modify, relative to the submission
   directory.
3. Allowed file patterns. Default to the narrowest useful set.
4. Run command containing `{config_path}`.
5. Optional smoke command containing `{config_path}`.
6. Config-template path relative to `source.dir`.
7. Headline metric and whether it should be minimized or maximized.
8. Daily LLM budget.
9. Whether the Coder may modify source files. Default to `false`.

If the human does not yet have a real executor, offer two honest choices:

- create only the validated lab shell and stop before execution; or
- copy the synthetic executor shape from
  `examples/smoke-lab/` to test the plumbing, clearly labelling its results as
  unrelated to the human's scientific claim.

Write `<submission>/lab.yaml`. Use this shape:

```yaml
lab_id: example-lab
domain: example-domain

source:
  dir: .
  allowed_patterns: ["src/**/*.py", "configs/**/*.yaml"]

executor:
  run_command: "python -m src.run --config {config_path}"
  smoke_command: "python -m src.run --config {config_path} --smoke"
  config_template: configs/default.yaml
  run_timeout_s: 7200
  smoke_timeout_s: 300

metrics:
  headline: { column: validation_score, direction: max }
  panels:
    - { column: validation_score, label: "Validation score", direction: max }
  flat_digest_epsilon: 0.005

budget:
  daily_cap_usd: 10.0
  sonnet_default: true

autonomy:
  coder_enabled: false
```

Adapt the values; do not copy placeholders into a real lab. Keep credentials in
the environment or `<submission>/.env`, never in `lab.yaml` or git.

## 5. Validate and present the launch contract

Run:

```bash
.venv/bin/efferents validate --submission <submission>
```

Fix field-level errors until validation succeeds. Then present a concise launch
contract containing:

- lab id and domain;
- hypothesis title and falsifier;
- source directory and allowed patterns;
- exact run and smoke commands;
- headline metric and direction;
- Coder enabled/disabled;
- daily budget;
- current placement: **private, unlinked**.

Ask for explicit approval before executing any repository-defined command.

## 6. Run the first bounded cycle

If the human wants a no-LLM plumbing check first:

```bash
.venv/bin/efferents start --submission <submission> --dry-run --max-iterations 1
```

If `ANTHROPIC_API_KEY` is available and the human approved real execution:

```bash
.venv/bin/efferents start --submission <submission> --max-iterations 3
```

Do not detach the first run. Keep it bounded so the human can inspect what the
lab does. Then open the workspace:

```bash
.venv/bin/efferents serve --lab-root <submission>/lab
```

Report the local URL. Show the first hypothesis, run ledger, budget, agent log,
and any paper/memo produced. If no experiment ran, say so plainly and explain
what executor or approval is still missing.

## 7. Ask where the lab belongs

Only after the human has reviewed the hypothesis and launch contract, ask:

> Keep this lab in your private research group, or prepare it as a public lab
> on efferents.com?

### Private research group — default

- Keep the full lab state in its isolated local environment.
- Do not publish or sync hypotheses, papers, metrics, logs, source, or data.
- Other labs and other users receive no feed access and share no files with it.
- Explain that team invitations/private hosted group sync are a future platform
  capability; the framework's working privacy boundary today is local storage.

### Public lab — explicit opt-in

- Explain exactly what may eventually be published: lab identity/domain, the
  approved seed hypothesis, accepted paper bundles, metric provenance, and
  optional code repository/commit references.
- Explain what must never be published automatically: credentials, `.env`, raw
  datasets, arbitrary source files, private logs, or unaccepted drafts.
- Ask the human to approve the publication manifest before any network write.
- The hosted registration/publishing API is not implemented in this framework
  repository yet. Do not claim that the lab was added to efferents.com. Leave
  it private and report it as **ready to link** when the hosted surface ships.

Changing from private to public must always be an explicit later action. Making
a public lab private stops future publication; it cannot silently erase
artifacts that were already made public.

## 8. Handoff

Report:

- lab id and local path;
- first hypothesis path;
- validation and first-run outcome;
- dashboard command;
- placement choice and whether it is local, ready to link, or linked;
- how to start a longer run, only if the human wants one:

```bash
.venv/bin/efferents start --submission <submission> --detach
.venv/bin/efferents status --lab-id <lab-id>
```

The human remains the owner of the lab and can stop it with:

```bash
.venv/bin/efferents stop --lab-id <lab-id>
```
