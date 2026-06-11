from pathlib import Path

LANDING = Path(__file__).resolve().parents[1] / "web" / "landing" / "index.html"


def test_landing_exists():
    assert LANDING.is_file()


def test_landing_has_agent_instruction():
    html = LANDING.read_text()
    assert "intake.md" in html
    assert "Read https://efferents.com/intake.md and follow it" in html


def test_landing_links_stylesheet():
    assert 'href="style.css"' in LANDING.read_text()
