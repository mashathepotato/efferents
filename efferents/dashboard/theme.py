"""Canonical visual contract for Efferents research surfaces.

The live dashboard stylesheet is the source of truth. Example applications may
add view-specific layout rules, but they must embed this contract instead of
inventing a second palette, typography stack, or theme policy.
"""

from __future__ import annotations

from pathlib import Path


RESEARCH_THEME_ID = "efferents-research-lab-v1"
THEME_CSS_MARKER = "/*__EFFERENTS_RESEARCH_THEME_CSS__*/"
THEME_ID_MARKER = "__EFFERENTS_RESEARCH_THEME_ID__"

_STATIC_DIR = Path(__file__).resolve().parent / "static"
RESEARCH_THEME_CSS = (_STATIC_DIR / "dashboard.css").read_text()


def embed_research_theme(page: str) -> str:
    """Replace the required theme markers in a self-contained HTML page."""
    if page.count(THEME_CSS_MARKER) != 1 or page.count(THEME_ID_MARKER) != 1:
        raise ValueError("page must contain exactly one Efferents theme CSS and ID marker")
    return (
        page.replace(THEME_CSS_MARKER, RESEARCH_THEME_CSS)
        .replace(THEME_ID_MARKER, RESEARCH_THEME_ID)
    )
