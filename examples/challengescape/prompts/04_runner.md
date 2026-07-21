# Runner (not an LLM)

The runner is `efferents run <lab_dir> --approve --out <lab_dir>/out` — a
deterministic subprocess loop, no model calls. It executes the lab's own
`train_command`/`eval_command` per sweep point, enforces the wall-clock
budget, and writes `journal/001–004`, `runs.jsonl`, `claims.jsonl`,
`dashboard.html`.

**Stub fallback:** if a lab's science breaks close to a deadline,
`efferents demo smoke-lab --out <dir>` produces the same artifact shape from
the built-in toy lab — label it as the stub it is.
