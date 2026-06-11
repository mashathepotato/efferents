"""Journal feed renderer: paper markdown files -> feed-card data.

Pure and side-effect-free. It is handed a list of paper file paths and knows
nothing about where they come from (a local lab/paper/ dir now, a cloned
efferents-journal git repo later). That ignorance is the seam between the
local-first build and the git-backed shared journal.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

_REQUIRED = ("lab_id", "campaign_id", "novelty_claim", "published_at", "status")


class FeedCard(BaseModel):
    lab_id: str
    campaign_id: str
    title: str
    summary: str
    novelty_claim: str
    status: str
    published_at: str


def render_feed(paper_paths: list[Path]) -> list[FeedCard]:
    """Parse paper markdown files into feed cards, newest-first.

    Malformed papers (no frontmatter, missing required fields, bad YAML) are
    skipped, never raised.
    """
    cards: list[FeedCard] = []
    for path in paper_paths:
        card = _card_from_path(Path(path))
        if card is not None:
            cards.append(card)
    cards.sort(key=lambda c: c.published_at, reverse=True)
    return cards


def _card_from_path(path: Path) -> FeedCard | None:
    try:
        text = path.read_text()
    except OSError:
        return None
    front, body = _split_frontmatter(text)
    if front is None:
        return None
    try:
        meta = yaml.safe_load(front) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict) or any(k not in meta for k in _REQUIRED):
        return None
    novelty = str(meta["novelty_claim"])
    return FeedCard(
        lab_id=str(meta["lab_id"]),
        campaign_id=str(meta["campaign_id"]),
        title=_extract_title(body, novelty),
        summary=novelty,
        novelty_claim=novelty,
        status=str(meta["status"]),
        published_at=str(meta["published_at"]),
    )


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split a `---\\n{yaml}\\n---\\n\\n{body}` document. Returns (yaml, body)."""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1], parts[2]


def _extract_title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") or stripped == "#":
            return stripped.lstrip("#").strip()
    return fallback[:80]
