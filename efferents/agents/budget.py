"""Spend tracking, daily cap, model routing.

Pricing as of late 2025 (per million tokens):

    claude-opus-4-7    : $15 in, $75 out
    claude-sonnet-4-6  : $3 in, $15 out
    claude-haiku-4-5   : $1 in, $5 out

Cache pricing (relative to input):
    cache_creation_input_tokens : 1.25x base input
    cache_read_input_tokens     : 0.1x base input

These constants are baked in. Update if Anthropic changes pricing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from efferents.agents.state import append_jsonl, read_jsonl

PRICING_PER_MTOK = {
    "claude-opus-4-7":    {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":  {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":   {"input":  1.00, "output":  5.00},
}

CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10

# Default model routing per agent role.
ROLE_MODEL = {
    "researcher": "claude-sonnet-4-6",  # legacy fallback; dialogue uses student/supervisor
    "student":    "claude-sonnet-4-6",
    "supervisor": "claude-sonnet-4-6",  # may escalate to Opus via model_for_supervisor()
    "executor":   None,   # Executor doesn't call Anthropic
    "analyst":    "claude-opus-4-7",
    "writer":     "claude-sonnet-4-6",
    "coder":      "claude-opus-4-7",  # architectural code edits need careful reasoning
    "librarian":  "claude-sonnet-4-6",  # synthesis + web_search; not Opus-grade reasoning
    "reviewer":   "claude-sonnet-4-6",  # 3x per submission; one critical/neutral/enthusiast
    "rebuttal":   "claude-sonnet-4-6",  # 1x per submission; student-voiced reply
}

SUPERVISOR_OPUS_STREAK_THRESHOLD = 2


@dataclass(frozen=True)
class CallUsage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


def cost_usd(model: str, usage: CallUsage) -> float:
    p = PRICING_PER_MTOK.get(model)
    if p is None:
        return 0.0
    base_in = p["input"] / 1_000_000
    base_out = p["output"] / 1_000_000
    return (
        usage.input_tokens * base_in
        + usage.output_tokens * base_out
        + usage.cache_creation_input_tokens * base_in * CACHE_WRITE_MULT
        + usage.cache_read_input_tokens * base_in * CACHE_READ_MULT
    )


def utc_date_str(ts: str | None = None) -> str:
    dt = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d")


class BudgetTracker:
    """Append-only ledger of every Anthropic call; soft daily ceiling."""

    def __init__(self, ledger_path: Path, daily_cap_usd: float = 100.0):
        self.path = ledger_path
        self.daily_cap = daily_cap_usd

    def record(
        self,
        *,
        agent: str,
        model: str,
        usage: CallUsage,
        cache_hit_rate: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        ts = datetime.now(timezone.utc).isoformat()
        record = {
            "ts": ts,
            "agent": agent,
            "model": model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_creation_input_tokens": usage.cache_creation_input_tokens,
            "cache_read_input_tokens": usage.cache_read_input_tokens,
            "cost_usd": cost_usd(model, usage),
            "cache_hit_rate": cache_hit_rate,
            "notes": notes,
        }
        append_jsonl(self.path, record)
        return record

    def spend_today(self, today: str | None = None) -> float:
        today = today or utc_date_str()
        return sum(
            r["cost_usd"]
            for r in read_jsonl(self.path)
            if r.get("ts", "").startswith(today)
        )

    def spend_total(self) -> float:
        return sum(r.get("cost_usd", 0.0) for r in read_jsonl(self.path))

    def cache_stats(self, n_recent: int = 50) -> dict[str, float]:
        recs = read_jsonl(self.path)[-n_recent:]
        creates = sum(r.get("cache_creation_input_tokens", 0) or 0 for r in recs)
        reads = sum(r.get("cache_read_input_tokens", 0) or 0 for r in recs)
        ins = sum(r.get("input_tokens", 0) or 0 for r in recs)
        denom = max(1, ins + creates + reads)
        return {
            "n_calls": len(recs),
            "cache_read_share": reads / denom,
            "cache_create_share": creates / denom,
            "fresh_input_share": ins / denom,
        }

    def should_pause(self) -> bool:
        return self.spend_today() >= self.daily_cap


def model_for(role: str, override: str | None = None) -> str | None:
    if override:
        return override
    return ROLE_MODEL.get(role)


def model_for_supervisor(saturation_streak: int) -> str:
    """Supervisor escalates to Opus when the saturation score has been high
    for ``SUPERVISOR_OPUS_STREAK_THRESHOLD`` consecutive iterations — the loop
    is genuinely stuck and Sonnet's pivots aren't landing."""
    if saturation_streak >= SUPERVISOR_OPUS_STREAK_THRESHOLD:
        return "claude-opus-4-7"
    return ROLE_MODEL["supervisor"]
