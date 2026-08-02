from pathlib import Path
import struct

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


def test_landing_has_generated_network_hero():
    html = LANDING.read_text()
    image = LANDING.parent / "img" / "efferents-network.png"

    assert 'src="img/efferents-network.png"' in html
    assert "autonomous research-lab nodes" in html
    assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", image.read_bytes()[16:24])
    assert width >= 1400
    assert width / height >= 1.4


def test_landing_explains_private_and_public_destinations():
    html = LANDING.read_text()
    assert "Alongside your own work" in html
    assert "Across research groups" in html
    assert "Publication requires your approval" in html


def test_landing_speaks_to_researchers_and_explains_why_now():
    html = LANDING.read_text()
    assert "Tired of babysitting tedious optimization?" in html
    assert "Have an idea you want tested while you sleep?" in html
    assert "Want to go beyond what is known—not just tune around it?" in html
    assert "You keep the judgment. The lab takes the repetition." in html
    assert "Research throughput now compounds." in html
    assert "Automate one part to keep up. Connect auditable loops to get ahead." in html


def test_landing_links_stylesheet():
    assert 'href="style.css"' in LANDING.read_text()


def test_landing_defaults_to_light_lab_theme():
    html = LANDING.read_text()
    css = STYLES.read_text()
    assert '<meta name="color-scheme" content="light">' in html
    assert '<meta name="theme-color" content="#ffffff">' in html
    assert "color-scheme: light;" in css
    assert "--bg: #ffffff;" in css
    assert "--signal: #003b80;" in css
    assert "--line: #003b80;" in css
    assert "--on-signal: #ffffff;" in css
    assert "--data: #003b80;" in css
    assert "--mustard: #d4a017;" in css
    assert "--orange: #f06c00;" in css
    assert "color: var(--orange);" in css
    assert "#03befc" not in css
    assert "#0057ff" not in css
    assert "--display:" in css
    assert "--sans: var(--display);" in css
    assert 'content: "ℯ";' in css
    assert 'content: "EF";' not in css
    assert "linear-gradient" not in css
    assert "backdrop-filter" not in css
