"""Shared file/DB I/O for the agent loop.

Layout under lab/:
    runs.sqlite       per-run results (schema in auto_qml/run.py)
    queue.jsonl       Researcher -> Executor handoff (one JSON proposal per line)
    lab_notebook.md   running narrative, agent-only writes, append-only
    digests/          Analyst summaries, one timestamped markdown per write
    budget.jsonl      per-call spend records (one JSON per line)
    state.json        misc orchestrator state (last_digest_at, last_run_id, ...)
    knowledge/        librarian-managed lit-review cache
        kb.sqlite     topics + papers tables (see agents/librarian.py)
    librarian_log.jsonl  per-call librarian record (parallel to coder_log.jsonl)
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LabPaths:
    root: Path
    runs_db: Path
    queue: Path
    notebook: Path
    digests_dir: Path
    budget: Path
    state: Path
    knowledge_dir: Path
    kb_db: Path
    librarian_log: Path


def lab_paths(root: str | Path = "lab") -> LabPaths:
    r = Path(root)
    return LabPaths(
        root=r,
        runs_db=r / "runs.sqlite",
        queue=r / "queue.jsonl",
        notebook=r / "lab_notebook.md",
        digests_dir=r / "digests",
        budget=r / "budget.jsonl",
        state=r / "state.json",
        knowledge_dir=r / "knowledge",
        kb_db=r / "knowledge" / "kb.sqlite",
        librarian_log=r / "librarian_log.jsonl",
    )


def init_lab(paths: LabPaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.digests_dir.mkdir(parents=True, exist_ok=True)
    paths.knowledge_dir.mkdir(parents=True, exist_ok=True)
    if not paths.notebook.exists():
        paths.notebook.write_text(
            "# Lab notebook\n\n"
            "Agent-only, append-only running narrative. "
            "Each run appends one entry; each digest appends a pointer.\n\n"
            f"Initialized {datetime.now(timezone.utc).isoformat()}.\n\n"
        )
    if not paths.queue.exists():
        paths.queue.touch()
    if not paths.budget.exists():
        paths.budget.touch()
    if not paths.state.exists():
        paths.state.write_text(json.dumps({}))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def recent_runs(db_path: Path, n: int = 30) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT run_id, started_at, seed, model, raw_q, epochs, aug_depth,
                   aug_shared_unitary, cond_drop_p, eval_kind, eval_n,
                   val_x0_mse, e_w1, active_frac_w1, radial_l2, radial_l2_log,
                   duration_seconds, config_hash, notes, samples_png,
                   campaign_id, researcher_mode
            FROM runs ORDER BY started_at DESC LIMIT ?
            """,
            (n,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def runs_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
    finally:
        conn.close()


def notebook_tail(path: Path, max_chars: int = 8000) -> str:
    if not path.exists():
        return ""
    text = path.read_text()
    if len(text) <= max_chars:
        return text
    return "...[truncated head]...\n" + text[-max_chars:]


def notebook_append(path: Path, entry: str) -> None:
    with path.open("a") as f:
        f.write(entry.rstrip() + "\n\n")


def queue_push(path: Path, proposal: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(proposal) + "\n")


def queue_pop(path: Path) -> dict[str, Any] | None:
    """Pop the first line. Naive but adequate for a single-orchestrator loop."""
    if not path.exists():
        return None
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    if not lines:
        return None
    head, rest = lines[0], lines[1:]
    path.write_text("\n".join(rest) + ("\n" if rest else ""))
    return json.loads(head)


def queue_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for ln in path.read_text().splitlines() if ln.strip())


def read_context(context_dir: str | Path = "context") -> dict[str, str]:
    """Load human-curated context files used by Researcher / Analyst prompts."""
    cd = Path(context_dir)
    out: dict[str, str] = {}
    for name in ("vision.md", "decisions.md", "research_log.md"):
        p = cd / name
        if p.exists():
            out[name] = p.read_text()
    return out


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text() or "{}")
    except json.JSONDecodeError:
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2))


class StudentStateView:
    """Read/write view onto a per-student slice of state.json (Phase B).

    For the DEFAULT_STUDENT_ID, reads/writes go to the top-level state dict
    (backward-compat with Phase A's flat layout). For other students, reads
    /writes are nested under state["students"][<student_id>].

    The view is backed by `state` — modifications through this view mutate
    the underlying dict in place. Caller still needs to save_state() to
    persist.
    """

    __slots__ = ("_state", "_student_id", "_flat")

    def __init__(self, state: dict[str, Any], student_id: str):
        # Lazy import to avoid a circular dependency at module-load time.
        from efferents.lab import DEFAULT_STUDENT_ID  # noqa: PLC0415
        self._state = state
        self._student_id = student_id
        self._flat = (student_id == DEFAULT_STUDENT_ID)

    @property
    def scope(self) -> dict[str, Any]:
        """The actual dict where this student's cursors live."""
        if self._flat:
            return self._state
        students = self._state.setdefault("students", {})
        return students.setdefault(self._student_id, {})

    def get(self, key: str, default: Any = None) -> Any:
        return self.scope.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.scope[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.scope[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self.scope

    def update(self, mapping: dict[str, Any]) -> None:
        self.scope.update(mapping)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def retry_hint(parse_error: str, must_contain: str | None) -> str:
    """Standard nudge appended to a retry call after a JSON parse failure.

    Used by `parse_json_with_one_retry`; exposed so tests + tool-use loops
    can compose the same hint into their own message stream.
    """
    hint = (
        f"Your previous output failed JSON parsing: `{parse_error}`. "
        "Emit STRICT JSON now. First character must be `{`. No prose, no "
        "code fences."
    )
    if must_contain:
        hint += f" The JSON must contain {must_contain}."
    return hint


def parse_json_with_one_retry(
    *,
    call_fn,
    must_contain: str | None = None,
    fallback: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Call once; on JSON parse failure, retry once with the parse error fed
    back into the prompt. Returns (parsed_dict, status) where status is one
    of "ok" (first try parsed), "retried" (second try parsed), or "failed"
    (both attempts failed; returns ``fallback or {}``).

    `call_fn(retry_messages)` is the API-invoker closure:
      - On the first call, `retry_messages` is None.
      - On the retry, `retry_messages` is a list of message dicts the caller
        should APPEND to its existing message history before re-invoking the
        model. Conventionally these are an assistant turn echoing the failed
        text and a user turn carrying ``retry_hint(error, must_contain)``.
    Caller composes the actual API request inside `call_fn`; this helper
    only owns parse + retry-shape decisions.
    """
    text = call_fn(None)
    try:
        return parse_json_loose(text, must_contain=must_contain), "ok"
    except json.JSONDecodeError as e:
        retry_messages = [
            {"role": "assistant", "content": [{"type": "text", "text": text}]},
            {"role": "user", "content": [
                {"type": "text", "text": retry_hint(str(e), must_contain)}
            ]},
        ]
        text2 = call_fn(retry_messages)
        try:
            return parse_json_loose(text2, must_contain=must_contain), "retried"
        except json.JSONDecodeError:
            return (fallback or {}), "failed"


def parse_json_loose(text: str, *, must_contain: str | None = None) -> dict[str, Any]:
    """Robust JSON extraction. Handles raw JSON, fenced ```json ... ``` blocks,
    and prose+JSON. If `must_contain` is given, only balanced {...} substrings
    containing that key are considered (e.g. '"proposals"' or '"edits"').
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    starts = [i for i, c in enumerate(text) if c == "{"]
    for start in starts:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    if must_contain is None or must_contain in candidate:
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
                    break
    raise json.JSONDecodeError(
        f"no parseable JSON object{f' containing {must_contain!r}' if must_contain else ''} found",
        text,
        0,
    )


# ---------- Campaigns (Phase A) ----------

def campaign_insert(
    db_path: Path,
    *,
    id: str,
    lab_id: str,
    question: str,
    hypothesis_path: str,
    hypothesis_hash: str,
    opened_at: str | None = None,
    student_id: str = "primary",
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        # Detect whether the campaigns table has the Phase B student_id column.
        # Pre-migration DBs (in old tests / fresh-without-migration setups)
        # don't have it; in that case fall back to the 6-column INSERT so the
        # caller doesn't blow up.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(campaigns)").fetchall()}
        if "student_id" in cols:
            conn.execute(
                """INSERT INTO campaigns
                     (id, lab_id, question, hypothesis_path, hypothesis_hash, opened_at, student_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (id, lab_id, question, hypothesis_path, hypothesis_hash,
                 opened_at or now_iso(), student_id),
            )
        else:
            conn.execute(
                """INSERT INTO campaigns
                     (id, lab_id, question, hypothesis_path, hypothesis_hash, opened_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (id, lab_id, question, hypothesis_path, hypothesis_hash,
                 opened_at or now_iso()),
            )
        conn.commit()
    finally:
        conn.close()


def campaign_close(db_path: Path, id: str, *, reason: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE campaigns SET closed_at = ?, close_reason = ? WHERE id = ? AND closed_at IS NULL",
            (now_iso(), reason, id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"campaign {id!r} not found or already closed")
    finally:
        conn.close()


def campaign_open_list(db_path: Path, lab_id: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM campaigns WHERE lab_id = ? AND closed_at IS NULL",
            (lab_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def campaign_open_list_for_student(
    db_path: Path, lab_id: str, student_id: str
) -> list[dict[str, Any]]:
    """Open campaigns owned by a specific student. Used to enforce the
    per-student cap (auto_qml.lab.MAX_OPEN_CAMPAIGNS_PER_STUDENT).

    Falls back to all-lab-open if the campaigns table lacks the student_id
    column (pre-Phase-B migration). The fallback is conservative — it
    counts another student's open campaigns against this student's quota,
    which is fine for single-student labs."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(campaigns)").fetchall()}
        if "student_id" in cols:
            rows = conn.execute(
                "SELECT * FROM campaigns WHERE lab_id = ? AND student_id = ? AND closed_at IS NULL",
                (lab_id, student_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM campaigns WHERE lab_id = ? AND closed_at IS NULL",
                (lab_id,),
            ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def campaign_recently_closed_list(
    db_path: Path, lab_id: str, *, days: int = 7
) -> list[dict[str, Any]]:
    """Campaigns closed within the last `days` days. Used by the Researcher's
    Supervisor brief to surface closures (stale / published / rejected_by_review)
    so the Student stops proposing for them."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT * FROM campaigns
            WHERE lab_id = ? AND closed_at IS NOT NULL AND closed_at >= ?
            ORDER BY closed_at DESC
            """,
            (lab_id, cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def campaign_stale_open(
    db_path: Path, lab_id: str, *, hours: float = 48.0
) -> list[dict[str, Any]]:
    """Open campaigns where the most recent associated run (or, if no runs,
    `opened_at`) is older than `hours`."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT c.* FROM campaigns c
            LEFT JOIN runs r ON r.campaign_id = c.id
            WHERE c.lab_id = ? AND c.closed_at IS NULL
            GROUP BY c.id
            HAVING COALESCE(MAX(r.started_at), c.opened_at) < ?
            """,
            (lab_id, cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
