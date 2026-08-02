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
    assert "Hypothesis → run → review." in html
    assert "Evidence is the result." in html
    assert "Stop manually brokering" not in html


def test_landing_links_stylesheet():
    assert 'href="style.css"' in LANDING.read_text()


def test_landing_defaults_to_light_lab_theme():
    html = LANDING.read_text()
    css = STYLES.read_text()
    assert '<meta name="color-scheme" content="light">' in html
    assert '<meta name="theme-color" content="#ffffff">' in html
    assert "color-scheme: light;" in css
    assert "--bg: #ffffff;" in css
    assert "--signal: #03befc;" in css
    assert "#0057ff" not in css
    assert "--display:" in css
    assert "--sans: var(--display);" in css
    assert 'content: "ℯ";' in css
    assert 'content: "EF";' not in css
    assert "linear-gradient" not in css
    assert "backdrop-filter" not in css
