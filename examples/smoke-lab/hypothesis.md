---
slug: smoke-coefficient
falsifiability_gate: passed
status: active
created_at: 2026-05-26T00:00:00Z
---

# Smoke-lab hypothesis: optimal coefficient for synthetic loss

## Background

This is a deliberately trivial lab whose purpose is to exercise the efferents
framework plumbing end-to-end. It is **not** real research.

## Claim

The `coefficient` parameter that minimizes `synthetic_loss` lies in the
interval (0.75, 0.85). Outside this interval, `synthetic_loss` increases.

## Falsifier

A run with `coefficient` in [0.75, 0.85] should yield `synthetic_loss < 0.05`.
A run with `coefficient` outside that interval should yield
`synthetic_loss >= 0.05`. Either pattern being violated for >50% of runs
falsifies the claim.

## Probes (recorded by popper-probe)

- **Probe 1 (specificity)**: passed — interval is bounded.
- **Probe 2 (refutability)**: passed — concrete numeric threshold.
- **Probe 3 (verifiability)**: passed — measurable in a single run.
