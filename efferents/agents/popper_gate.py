"""Headless Popper Probe intake for the orchestrator.

Single-shot self-play: load SKILL.md as system prompt, ask the model to
play both roles (claimant + Popperian probe) and emit ONLY the
hypothesis.md contents. Subprocess-validate with popper-probe's existing
CLI. One retry on validator fail.

Popper-probe repo location: env POPPER_PROBE_REPO, default ~/Documents/popper-probe.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _popper_repo() -> Path:
    return Path(os.environ.get("POPPER_PROBE_REPO", str(Path.home() / "Documents/popper-probe")))


def _skill_md() -> str:
    return (_popper_repo() / "skills/intake/SKILL.md").read_text()


def _validator() -> Path:
    return _popper_repo() / "scripts/validate_hypothesis.py"


_HEADLESS_INSTRUCTION = """
HEADLESS MODE — IMPORTANT

You are running without an interactive user. Play BOTH roles yourself:
the claimant (using the draft claim below as their starting position)
AND the Popperian probe. Run Probes 1, 2, and 3 internally. Probe 0
(SoTA orientation) is skipped. Probe 4 (distinctiveness) is recorded as
flagged or substantive.

If Probe 1 or Probe 2 cannot be satisfied even after a real sharpening
attempt, emit a hypothesis.md with `falsifiability_gate: failed`,
`status: unfalsifiable`, and a `## Diagnostic` section. Otherwise emit
`falsifiability_gate: passed`, `status: active`, and the full body
sections per the schema.

Output ONLY the hypothesis.md file contents (YAML frontmatter +
markdown body). No commentary, no code fences, no preamble. Your first
character must be a literal "---" opening the frontmatter.
""".strip()


@dataclass
class GateResult:
    ok: bool
    path: Path | None
    hash: str | None
    reason: str | None  # populated on failure


def _hash_file(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def _extract_text(response: Any) -> str:
    return "".join(block.text for block in response.content if getattr(block, "type", "text") == "text")


def _validate(path: Path) -> tuple[bool, str]:
    v = _validator()
    if not v.exists():
        return False, f"validator not found: {v} (check POPPER_PROBE_REPO)"
    try:
        proc = subprocess.run(
            [sys.executable, str(v), str(path)],
            capture_output=True, text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False, "validator timed out after 10s"
    return (proc.returncode == 0, (proc.stderr or proc.stdout).strip())


def run_gate(
    *,
    draft_claim: str,
    slug: str,
    corpus_root: Path,
    client: Any,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
) -> GateResult:
    """Run single-shot self-play intake. Writes hypothesis.md on success.

    Returns GateResult with ok=True/path/hash on accept, or ok=False/reason
    on drop after one retry.
    """
    out_dir = corpus_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "hypothesis.md"

    system = _skill_md() + "\n\n" + _HEADLESS_INSTRUCTION

    user_first = (
        f"Draft claim to process:\n\n{draft_claim}\n\n"
        f"Emit the hypothesis.md for slug `{slug}` now."
    )
    last_errors = ""

    for attempt in (1, 2):
        if attempt == 1:
            user_msg = user_first
        else:
            user_msg = (
                f"{user_first}\n\n"
                f"Your previous output failed validate_hypothesis.py with:\n\n"
                f"{last_errors}\n\n"
                f"Emit a corrected hypothesis.md. Same output rules apply."
            )
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        body = _extract_text(response)
        out_path.write_text(body)
        ok, errors = _validate(out_path)
        if ok:
            return GateResult(ok=True, path=out_path, hash=_hash_file(out_path), reason=None)
        last_errors = errors

    return GateResult(ok=False, path=None, hash=None, reason=f"validate failed: {last_errors}")
