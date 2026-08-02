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
CHALLENGE_REPORT = (
    ROOT
    / "examples"
    / "challengescape"
    / "labs"
    / "lab_01_reasoning_verification"
    / "out"
    / "dashboard.html"
)


def test_theme_contract_is_light_first_and_high_information():
    assert RESEARCH_THEME_CSS.startswith(":root {\n  color-scheme: light;")
    assert ':root[data-theme="dark"]' in RESEARCH_THEME_CSS
    assert "--bg: #ffffff;" in RESEARCH_THEME_CSS
    assert "--signal: #003b80;" in RESEARCH_THEME_CSS
    assert "--line: #003b80;" in RESEARCH_THEME_CSS
    assert "--on-signal: #ffffff;" in RESEARCH_THEME_CSS
    assert "--data: #003b80;" in RESEARCH_THEME_CSS
    assert "--mustard: #d4a017;" in RESEARCH_THEME_CSS
    assert "--orange: #f06c00;" in RESEARCH_THEME_CSS
    assert RESEARCH_THEME_CSS.count("#d4a017") == 2
    assert RESEARCH_THEME_CSS.count("#f06c00") == 2
    assert "#03befc" not in RESEARCH_THEME_CSS
    assert "#0057ff" not in RESEARCH_THEME_CSS
    assert "--display:" in RESEARCH_THEME_CSS
    assert "--sans: var(--display);" in RESEARCH_THEME_CSS
    assert "color-mix" not in RESEARCH_THEME_CSS
    assert "backdrop-filter" not in RESEARCH_THEME_CSS
    assert "#356f50" not in RESEARCH_THEME_CSS
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
    assert "color-mix" not in page
    assert "#2a78d6" not in page
    assert "border-radius: 12px" not in page
    assert 'content: "ℯ";' in page
    assert 'content: "EF";' not in page
    assert 'id="theme-button"' in page
    assert "grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));" in page


def test_every_example_html_app_uses_the_theme_contract():
    offenders = []
    for path in (ROOT / "examples").rglob("*.py"):
        source = path.read_text()
        if "<!doctype html" in source.lower() and "embed_research_theme" not in source:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_checked_in_challenge_report_uses_current_report_theme():
    report = CHALLENGE_REPORT.read_text()

    assert 'content: "efferents / research record";' in report
    assert "--sans: var(--display);" in report
    assert "--signal: #003b80;" in report
    assert "--mustard: #d4a017;" in report
    assert "--orange: #f06c00;" in report
    assert "#03befc" not in report
    assert "#b9f36a" not in report
    assert 'content: "EF / RESEARCH RECORD";' not in report
