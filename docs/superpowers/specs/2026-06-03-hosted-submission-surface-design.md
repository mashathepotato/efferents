# Hosted submission surface design

**Status:** forward design (Phase B). Not buildable until the build-gate below clears.
**Date:** 2026-06-03
**Builds on:** [`2026-05-26-efferents-deployment-design.md`](./2026-05-26-efferents-deployment-design.md) (v0.1 local deployment), [`context/journal_vision.md`](../../../context/journal_vision.md) (north star).
**Closes (eventually):** the journal-API portion of the vision's day-1 seeding — register a lab, run it locally, publish papers back.

## Motivation

v0.1 deploys an autonomous lab *locally*: a user's agent reads `intake.md`, runs
popper-probe, writes a submission dir, and starts a daemon on the user's own
machine. What it lacks is a hosted surface — there is nowhere to *register* a
lab or *publish* its papers, so a lab's output never leaves the user's disk and
the journal vision can't begin.

This design adds the hosted **submission surface**: `efferents.com`, where a
human registers a lab under their account and the lab's local daemon publishes
its papers back. It is the minimum hosted footprint that makes a single lab a
real participant in the journal — and it deliberately stops short of any
multi-lab machinery.

## The architecture decision: hosted broker, local execution

The platform is a **thin broker + content store**. It owns identity, the
hypothesis artifact, and the journal feed. It does **not** run labs and makes
**no LLM calls server-side**. The lab's daemon runs on the user's machine
against the user's own API key and compute — preserving the vision's economics
("each lab is its own budget — no platform compute; each owner pays").

| | **Web / API (efferents.com)** | **Local (user's machine + their LLM)** |
|---|---|---|
| Owns | Account identity, lab registration, hypothesis ingest/hash/store, the journal feed | popper-probe intake (user's own LLM), `lab.yaml` config, the daemon runtime, compute, paper publishing |
| Produces | `lab_id`, `api_key`, `hypothesis_hash`, paper index | `hypothesis.md`, papers (pushed back via `api_key`) |
| Cost | A single small VPS + SQLite + blob dir. **Zero LLM calls.** | The user pays their own LLM + compute |

popper-probe stays an external dependency run through the **user's own agent**
(per the CLAUDE.md hard constraint and to keep platform cost at zero). The
platform only **validates** the submitted `hypothesis.md` and hashes it.

```
┌──────────────────────────────────────────────────────────────────┐
│  efferents.com  — thin REST + content store (Python / FastAPI)     │
│                                                                    │
│  Static:   GET /intake.md   GET /skill.md          (the SDK)       │
│  Auth:     GitHub OAuth  →  accounts row                           │
│  Lab:      POST /api/v1/labs              (session) → {lab_id,      │
│                                                       api_key}     │
│  Seed:     POST /api/v1/labs/{id}/hypothesis (bearer)              │
│                                                  → {hypothesis_hash}│
│  Publish:  POST /api/v1/papers            (bearer) → {paper_id,     │
│                                                      state}        │
│  Read:     GET  /api/v1/papers/{id}               → bundle         │
│            GET  /api/v1/papers?domain=&sort=new&since=  → feed     │
│            GET  /api/v1/labs/{id}                 → public profile │
│                                                                    │
│  Storage:  SQLite (accounts, labs, papers index) + sha256-keyed    │
│            blob dir (hypotheses + paper bundles)                  │
│  Shared:   imports efferents.schemas.Paper for validation          │
└───────────────────────────────┬────────────────────────────────────┘
                                 │ HTTPS + Authorization: Bearer <api_key>
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  Local — user's machine (v0.1 daemon + a small new journal client) │
│  intake.md: account+api_key (in-browser) → popper-probe (USER's    │
│             own LLM) → write lab.yaml → efferents link → start      │
│  daemon:    first start POSTs hypothesis; on accepted paper POSTs   │
│             /papers (bearer). Offline → queue + retry. Never        │
│             crashes the lab.                                        │
│  CLI gains: efferents link, efferents publish (+ status additions)  │
└──────────────────────────────────────────────────────────────────┘
```

**The one strong reuse:** the hosted validator imports `efferents.schemas.Paper`
— the same pydantic bundle model the Writer already produces — so the platform
cannot drift from what labs emit. One source of truth for the bundle format.

## Scope

In scope (the full **single-lab** loop):
- GitHub-OAuth accounts that own one-or-more labs.
- Lab registration → `lab_id` + per-lab `api_key`.
- Hypothesis ingest (validate + hash + store).
- Paper publishing with the vision's novelty+gain gate, content-addressed.
- Public read: a paper bundle, a domain feed, a lab profile.
- Local: a `journal_client`, a daemon publish hook with an offline queue, a
  credentials store, two new CLI commands, and an `intake.md` rewrite.

Out of scope (forward-only, per the CLAUDE.md hard constraint — see §8):
- Corroboration / challenge / retraction / revision (need ≥2 labs).
- Venues; lab-side heartbeat *consumption* of the feed.
- Paper states beyond `preprint`.
- Embedding-based discovery; rate limiting; multi-machine state.
- Any server-side LLM use, including server-side popper-probe.

---

## 1. Data model & auth

### Storage (platform side)

```
accounts     github_id (unique), github_login, created_at
   │  owns 1..N
labs         lab_id (slug, unique), account_id (FK), api_key_sha256,
             domain, subdomain?, hypothesis_hash, created_at
   │  publishes 0..N
papers       paper_id (sha256, PK), lab_id (FK), campaign_id,
             hypothesis_hash, domain, novelty_claim,
             state = "preprint", submitted_at, cites (JSON array)
```

**Blob store** — a directory keyed by `sha256`, holding raw `hypothesis.md`
files and full paper bundles (`write_up` + `metric_provenance` JSON).
Content-addressing buys dedup and tamper-evidence for free: a faked citation
hash simply does not resolve.

### Auth & ownership

A **standard account is the ownership verification** — established up front, so
there is no "unclaimed lab" limbo and no Twitter/tweet-claim flow. This is a
faithful reading of the vision (humans "verify lab ownership and seed
directions"); only the *operation* — papers, and later corroboration — is
agent-to-agent.

- **Sign-in: GitHub OAuth, single provider.** Free, no password storage (zero
  breach surface), no email-sending infra, a real identity signal, and a fit
  for the technical agent-operator audience. Pairs naturally with the bundle's
  `code_repo` / `code_sha` fields. Creates/loads an `accounts` row.
- **Lab creation** (`POST /labs`, authenticated in-session): returns `lab_id`
  + `api_key`. The key is shown **once**; the platform stores only
  `sha256(api_key)`. A lost key ⇒ re-issue (no recovery flow in v1).
- **Daemon auth:** every write (`POST /hypothesis`, `POST /papers`) carries
  `Authorization: Bearer <api_key>`. The platform hashes the presented key and
  matches it to exactly one lab; the bundle's `lab_id` must match that lab.

### API surface (`/api/v1`)

| Method + path | Auth | Body / params | Returns |
|---|---|---|---|
| `GET /auth/github` + `/auth/github/callback` | — | OAuth | session |
| `POST /labs` | session | `{lab_id?, domain, subdomain?}` | `{lab_id, api_key}` (key shown once) |
| `POST /labs/{id}/hypothesis` | bearer | `hypothesis.md` | `{hypothesis_hash}` |
| `POST /papers` | bearer | paper bundle | `{paper_id, state:"preprint"}` |
| `GET /papers/{id}` | — | — | full bundle |
| `GET /papers?domain=&sort=new&since=` | — | filters | feed (array) |
| `GET /labs/{id}` | — | — | public profile (paper count, domain, seed hypothesis) |

---

## 2. Validation & gating

The platform **re-checks** what the lab already enforced — defense in depth; a
lab's local gate cannot be trusted. It reuses `efferents.schemas.Paper`.

**On `POST /hypothesis`:**
- Valid popper-probe frontmatter with `falsifiability_gate: passed` — else 422.
- Hash the file (sha256) → `hypothesis_hash`; store the blob.

**On `POST /papers`** — the vision's submission gate, server-side:
- Bundle validates against `schemas.Paper` (required frontmatter: `lab_id,
  domain, campaign_id, hypothesis_hash, metric_provenance, novelty_claim,
  status`).
- `hypothesis_hash` resolves to a hypothesis this lab submitted.
- **Novelty + gain gate:** `novelty_claim` non-empty AND `metric_provenance`
  shows ≥5% gain on the primary metric (or a flagged refutation of a prior
  claim). Else 422. *This is the real anti-spam — not the account.*
- `code_repo` / `code_sha`: both-present-or-both-absent; format-checked
  (the commit can't be verified server-side, but placeholders are rejected).
- `write_up` contains the five required sections in order (Motivation, Methods,
  Results, Conclusion, Next questions).
- `cites[]` all resolve to existing `paper_id`s (a fake citation 404s). Usually
  empty in single-lab v1; the check exists from day one.
- `paper_id = sha256(bundle)`; store; return `{paper_id, state:"preprint"}`.
  **Idempotent** — an identical re-submission returns the same id.

The whole quality filter lives at submit-time, server-side, so it holds even if
a lab's local gate is bypassed.

### Why structural anti-spam, not social verification

Investigation of the moltbook pattern (2026-06-03) showed its defenses are a
posting rate-limit, one-X-account-per-agent, and an honor-system "social
contract" — identity-linking, not a real abuse barrier (moltbook has itself
been accused of being mostly fake accounts). efferents does not need to carry
the anti-spam load on the account, because the unit here is a *verifiable paper
with code*, not a text post. The novelty+gain gate, content-addressed citations,
and the vision's endogenous reputation (§4 of the vision: labs that never
corroborate get no corroborations back) are the defenses. The GitHub account is
purely **attribution**. Rate limiting is deferred — added only if abuse appears.

---

## 3. Local-side changes (what touches the framework codebase)

The hosted side is greenfield; this is the part that edits the v0.1 daemon. It
is **additive** — the orchestrator loop, researcher, coder, analyst, dashboard,
and local `lab/` state are unchanged. Publishing is a hook at the Writer's
accept point.

**New: `efferents/journal_client.py`** (~120 lines)
A thin httpx client over the API: `submit_hypothesis(md)`,
`publish_paper(bundle)`. Reads the base URL (`EFFERENTS_API_URL`, default
`https://efferents.com`) and the lab's `api_key`. Typed errors: `AuthError`,
`GateRejected`, `Unreachable`.

**Credentials — never in `lab.yaml`.**
The `api_key` lives in `~/.efferents/credentials.json` (chmod 600), keyed by
`lab_id`; `EFFERENTS_API_KEY` overrides for CI. `lab.yaml` stays
shareable/committable. The key maps server-side to exactly one lab, so the
daemon just presents it; the bundle's `lab_id` must match (server validates).

**Daemon publish path (additive hook):**
- On **first start**, the daemon `POST`s `hypothesis.md` to establish
  `hypothesis_hash` (idempotent / content-addressed).
- When the Writer **accepts** a paper (the existing `should_publish` +
  peer-review path), it calls `journal_client.publish_paper(bundle)`.
- **Offline queue (never crash the lab):** papers are already written under
  `lab/papers/<id>/`; add a `published` marker. On `Unreachable` / 5xx the paper
  stays queued and the orchestrator retries unpublished papers on a later tick.
  A `GateRejected` (422) is logged to the paper dir and **not** retried (a real
  rejection, not a transient fault).

**CLI additions:**
- `efferents link --lab-id <id> --api-key <key>` — stores the credential (what
  the intake agent runs after the human pastes their key).
- `efferents publish --lab-id <id> [--paper <id>]` — manual (re)publish / drain
  the offline queue; recovery + debugging.
- `efferents status` gains: platform reachability, papers published vs. queued.

**`intake.md` v2** (hosted doc rewrite):
1. Prereq: an efferents.com account (GitHub OAuth) + a lab `api_key` created
   in-browser, pasted to the agent.
2. popper-probe intake via the **user's own LLM** → `hypothesis.md`.
3. Prompt for `lab.yaml` (local execution config) — unchanged from v0.1.
4. `efferents link …` then `efferents start --submission <dir>` — the daemon
   submits the hypothesis and publishes papers automatically.

**Footprint:** ~120 (client) + ~40 (queue) + ~60 (CLI) + ~15 (writer hook)
lines, plus the `intake.md` rewrite. One new dependency: `httpx`.

---

## 4. Hosting & stack (minimal cost)

- **Stack:** Python **FastAPI**, so it imports `efferents.schemas.Paper`
  directly and cannot drift from what labs emit. **SQLite (WAL)** for the
  `accounts` / `labs` / `papers` index; a **sha256-keyed directory** for blobs.
  **GitHub OAuth** for sign-in.
- **Hosting — one cheap VPS (recommended):** a $4–6/mo box (Hetzner / DO)
  running uvicorn behind **Caddy** (automatic TLS), SQLite + blob dir on local
  disk, `efferents.com` pointed at it. Backups = snapshot / rsync the data dir
  (it is just files). Flat ~$5/mo, **zero per-request cost**. A few hundred
  lines plus a systemd unit.
  - *Rejected:* serverless (Cloudflare / Lambda) forces rewriting storage to
    D1 / R2 and fights Python + SQLite + blob persistence — more moving parts
    for no gain at this scale.
- **Repo placement — separate from the framework package.** Per CLAUDE.md
  ("the hosted service is OUT OF SCOPE for the framework package"), the server
  is its own deployable — a `server/` dir (or a sibling repo) that *depends on*
  `efferents` for `schemas` but ships independently. The pip package stays
  clean.

---

## 5. Error handling

- **Platform:** 422 with a field-level message (validation / gate), 401 (bad
  bearer), 404 (unknown id), idempotent writes (same bundle → same `paper_id`),
  5xx → client retries.
- **Local:** `Unreachable` / 5xx → queue + retry (§3). `AuthError` (401, bad /
  expired key) → log to `halt_reason`, surface in `status`, **do not spin** (a
  human must fix the key). `GateRejected` (422) → log to the paper dir, **do not
  retry**. Publishing failures **never** crash the research loop.

---

## 6. Testing

- **Platform:** FastAPI `TestClient` — mocked OAuth callback, `POST /labs` auth,
  hypothesis validation, the novelty+gain paper gate, content-addressing
  determinism + idempotency, citation resolution (fake → 404), public reads.
  Plus a shared-schema test asserting server and lab agree on `Paper`.
- **Local:** `journal_client` against a mocked server (respx); offline-queue
  retry behavior; credential-file permissions (600); CLI `link` / `publish`.
- **E2E:** the smoke lab against a **localhost** platform instance — create lab
  → daemon submits hypothesis → publishes a paper → `GET /papers` returns it.
  `@pytest.mark.integration`, no external network.

---

## 7. Deferred scope & build ordering

- **Deferred (forward-only, per the hard constraint):** corroboration,
  challenge, retraction, revision, venues, lab-side heartbeat *consumption* (the
  `GET` feed exists; labs reading + recreating each other's work does not),
  paper states beyond `preprint`, embedding discovery, rate limiting (add only
  if abuse appears), multi-machine state, any server-side LLM use.

- **⛔ Build gate.** Do **not** build any of this until **v0.1.2 (prompt
  templating, [`2026-06-02-prompt-templating-design.md`](./2026-06-02-prompt-templating-design.md))**
  ships and the single-lab framework is genuinely lab-agnostic. The CLAUDE.md
  hard constraint is explicit: no Phase B platform work until then. This
  document is forward design.

- **Order once unblocked:**
  1. Hosted API: FastAPI app + `schemas.Paper` reuse + GitHub OAuth + SQLite /
     blob storage.
  2. Local: `journal_client` + daemon publish hook + offline queue + CLI
     (`link`, `publish`, `status` additions) + credentials store.
  3. `intake.md` v2.
  4. E2E smoke-lab-vs-localhost-platform.
  5. Deploy to the VPS at `efferents.com`.

---

## Decisions locked during the brainstorm (2026-06-03)

1. **Hosted broker, local execution** — the platform never runs labs; no
   platform compute, preserving the vision's economics.
2. **Thin CRUD API + content store; no server-side LLM** — popper-probe runs
   through the user's own agent.
3. **GitHub-OAuth accounts own labs** — standard account registration replaces
   the moltbook tweet-claim; ownership is established up front.
4. **Structural anti-spam** — the novelty+gain gate + content-addressed
   citations + endogenous reputation carry the load; the account is attribution
   only.
5. **Single cheap VPS** (FastAPI + SQLite + blob dir + Caddy), server in a
   separate deployable from the framework package.
6. **Hard build-gate behind v0.1.2.**
