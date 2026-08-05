"""Canonical chart runtime for Efferents research surfaces.

Charts are lab-owned data, framework-owned rendering: a lab declares what to
plot (its ``charts:`` config list, or nothing — specs are then inferred from
the run records themselves), and every surface renders those specs through the
same responsive runtime instead of hardcoding a fixed-size SVG per lab.

Example applications embed the runtime the same way they embed the research
theme: a single marker replaced at build time.
"""

from __future__ import annotations

from pathlib import Path


CHARTS_JS_MARKER = "/*__EFFERENTS_CHARTS_JS__*/"

_STATIC_DIR = Path(__file__).resolve().parent / "static"
CHARTS_JS = (_STATIC_DIR / "charts.js").read_text()


def embed_charts(page: str) -> str:
    """Replace the required charts marker in a self-contained HTML page."""
    if page.count(CHARTS_JS_MARKER) != 1:
        raise ValueError("page must contain exactly one Efferents charts marker")
    return page.replace(CHARTS_JS_MARKER, CHARTS_JS)
