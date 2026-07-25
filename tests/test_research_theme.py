from pathlib import Path
import runpy

import pytest

from efferents.dashboard.theme import (
    RESEARCH_THEME_CSS,
    RESEARCH_THEME_ID,
    embed_research_theme,
)


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "examples" / "challengescape" / "live.py"


def test_theme_contract_is_light_first_and_high_information():
    assert RESEARCH_THEME_CSS.startswith(":root {\n  color-scheme: light;")
    assert ':root[data-theme="dark"]' in RESEARCH_THEME_CSS
    assert "--mono:" in RESEARCH_THEME_CSS
    assert "border-radius: 0;" in RESEARCH_THEME_CSS


def test_theme_embedding_requires_both_contract_markers():
    with pytest.raises(ValueError, match="exactly one"):
        embed_research_theme("<html></html>")


def test_challengescape_embeds_canonical_theme_without_legacy_skin():
    page = runpy.run_path(str(LIVE))["PAGE"]

    assert f'data-efferents-theme="{RESEARCH_THEME_ID}"' in page
    assert "/*__EFFERENTS_RESEARCH_THEME_CSS__*/" not in page
    assert ":root {\n  color-scheme: light;" in page
    assert "prefers-color-scheme" not in page
    assert "#2a78d6" not in page
    assert "border-radius: 12px" not in page
    assert 'id="theme-button"' in page


def test_every_example_html_app_uses_the_theme_contract():
    offenders = []
    for path in (ROOT / "examples").rglob("*.py"):
        source = path.read_text()
        if "<!doctype html" in source.lower() and "embed_research_theme" not in source:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
