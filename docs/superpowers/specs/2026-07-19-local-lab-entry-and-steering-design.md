# Local lab entry and steering workspace

**Status:** implemented  
**Date:** 2026-07-19

## Context

The June web-surface design established a local, read-only observer. This
addendum extends that surface into the entry point for one local lab while
preserving the framework's core boundary: repository execution happens only on
the user's machine and only after explicit authorization.

The hosted registration, venue, and cross-lab journal remain out of scope.

## User flow

The workspace has four routes:

1. **Connect** — paste a GitHub repository or README URL. For development, an
   absolute local README/submission path is also accepted.
2. **Steer** — append a human instruction and optional one-cycle Researcher
   mode to the lab's auditable research log.
3. **Observe** — inspect the current hypothesis, metrics, run ledger, papers,
   budget, and agent activity.
4. **Network** — switch among local labs through a persistent portfolio rail,
   inspect node-level evidence, and view an operational topology. The public
   scope stays empty until an external registry is connected and a human has
   explicitly authorized publication.

The root route is the Connect page. Steer and Observe remain unavailable until
a lab has validated successfully.

## Submission discovery

For a GitHub source, the local server:

- accepts only `github.com` or `raw.githubusercontent.com` repository/README
  URLs;
- checks out the repository under
  `$EFFERENTS_HOME/checkouts/<owner>/<repo>`;
- first looks for `lab.yaml` and `hypothesis.md` beside the pasted README;
- otherwise accepts the sole valid submission directory in the repository;
- rejects zero or ambiguous submission candidates; and
- loads the submission through `LabConfig.from_submission`.

Connection initializes the submission's `lab/` state and registers it as
stopped. It never invokes the repository executor.

## Execution and steering

Starting and stopping are deliberately separate from connection. The user must
open a confirmation dialog, acknowledge the compute/LLM-cost boundary, and
confirm the action. Start additionally requires `ANTHROPIC_API_KEY` in the
process environment or submission `.env`.

A steering instruction is appended to:

```text
<submission>/context/research_log.md
```

Each record contains an ISO-8601 timestamp, a `Human steering` heading, the
instruction, and an optional `force_mode` value. Supported modes are `auto`,
`refine`, `moonshot`, `devils_advocate`, and `escape_to_code`.

## Local HTTP contract

Read endpoints:

- `GET /api/control`
- `GET /api/state`
- `GET /api/runs`
- `GET /api/papers`
- `GET /api/activity`
- `GET /api/labs`

Mutation endpoints:

- `POST /api/connect`
- `POST /api/steer`
- `POST /api/lab/start`
- `POST /api/lab/stop`
- `POST /api/labs/select`

The server binds to `127.0.0.1`. Every mutation requires the per-process token
returned by `/api/control` in `X-Efferents-CSRF`. Request bodies must be JSON and
are capped at 32 KiB. Responses are non-cacheable and set CSP, frame,
content-type, and referrer protections. API-key values are never returned.

## Visual system

The workspace uses a high-information research-console vocabulary: compact
monospace type, dense ledgers, explicit status fields, flat white surfaces, and
saturated blue rules and selections. Pale-blue fills, blur, and ambient shadows
are excluded. The light palette is the default. Dark mode is opt-in and
persisted in browser local storage.

There is no frontend build step and no third-party browser dependency.

## Verification

Tests cover GitHub URL parsing, submission validation/initialization, steering
records, start authorization, CSRF rejection, security headers, disconnected
API shapes, portfolio selection, CLI entry behavior, and the four UI routes.
Browser QA covers disconnected intake, a real connected smoke lab, topology
scope switching, evidence tracking, theme switching, and responsive layouts.
