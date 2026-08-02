from pathlib import Path

LANDING = Path(__file__).resolve().parents[1] / "web" / "landing" / "index.html"
STYLES = LANDING.with_name("style.css")


def test_landing_exists():
    assert LANDING.is_file()


def test_landing_has_agent_instruction():
    html = LANDING.read_text()
    assert "intake.md" in html
    assert (
        "Read https://raw.githubusercontent.com/mashathepotato/efferents/"
        "main/intake.md and follow it"
    ) in html


def test_landing_explains_private_and_public_destinations():
    html = LANDING.read_text()
    assert "Private research group" in html
    assert "Public lab" in html
    assert "Private by default" in html


def test_landing_explains_why_the_llm_research_loop_is_automated():
    html = LANDING.read_text()
    assert "LLM-written paper drafts" in html
    assert "LLM-written reviews" in html
    assert "The reproducible experiment" in html


def test_landing_links_stylesheet():
    assert 'href="style.css"' in LANDING.read_text()


def test_landing_defaults_to_light_lab_theme():
    html = LANDING.read_text()
    css = STYLES.read_text()
    assert '<meta name="color-scheme" content="light">' in html
    assert '<meta name="theme-color" content="#f7fbff">' in html
    assert "color-scheme: light;" in css
    assert "--bg: #f7fbff;" in css
    assert "--signal: #258fd2;" in css
