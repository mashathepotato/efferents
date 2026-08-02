from pathlib import Path

from efferents.dashboard.report_theme import REPORT_CSS


STATIC = Path(__file__).resolve().parents[1] / "efferents" / "dashboard" / "static"
PROGRESS = STATIC.parents[1] / "agents" / "progress.py"


def test_dashboard_has_portfolio_rail_and_network_map():
    html = (STATIC / "dashboard.html").read_text()
    javascript = (STATIC / "dashboard.js").read_text()

    assert 'id="lab-rail"' in html
    assert 'id="lab-list"' in html
    assert 'data-route-view="network"' in html
    assert 'id="lab-map"' in html
    assert 'data-network-scope="internal"' in html
    assert 'data-network-scope="public"' in html
    assert 'getJSON("/api/labs")' in javascript
    assert 'postJSON("/api/labs/select"' in javascript
    assert "renderNetwork();" in javascript


def test_shared_visual_contract_is_minimal_blue_and_white_research_console():
    css = (STATIC / "dashboard.css").read_text()
    html = (STATIC / "dashboard.html").read_text()
    progress = PROGRESS.read_text()

    assert "--bg: #ffffff;" in css
    assert "--panel: #ffffff;" in css
    assert "--panel-raised: #ffffff;" in css
    assert "--signal: #003b80;" in css
    assert "--accent: #03befc;" in css
    assert "#0057ff" not in css
    assert "--shadow: none;" in css
    assert "--display:" in css
    assert "--sans: var(--display);" in css
    assert html.count(">ℯ</span>") == 2
    assert ">EF</span>" not in html
    assert "color-mix" not in css
    assert "backdrop-filter" not in css
    assert "#f7fbff" not in css
    assert "#eef7fd" not in css
    assert "#356f50" not in css
    assert ".lab-list-item.selected" in css
    assert "overflow-wrap: anywhere;" in css
    assert "grid-template-columns: minmax(110px, .8fr) minmax(150px, 1.2fr);" in css
    assert ".lab-map" in css
    assert "color-scheme: light;" in REPORT_CSS
    assert "--signal: #003b80;" in REPORT_CSS
    assert "--accent: #03befc;" in REPORT_CSS
    assert "--sans: var(--display);" in REPORT_CSS
    assert 'content: "efferents / research record";' in REPORT_CSS
    assert 'content: "EF / RESEARCH RECORD";' not in REPORT_CSS
    assert "linear-gradient" not in REPORT_CSS
    assert "color-scheme: light;" in progress
    assert "#69ddd0" not in progress
    assert "#b9f36a" not in progress
    assert "--bg: #ffffff;" in progress
    assert "--signal: #003b80;" in progress
    assert "--accent: #03befc;" in progress
    assert "--sans: var(--display);" in progress
    assert "#f7fbff" not in progress
