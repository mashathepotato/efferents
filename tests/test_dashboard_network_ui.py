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


def test_shared_visual_contract_is_white_and_sky_blue():
    css = (STATIC / "dashboard.css").read_text()
    progress = PROGRESS.read_text()

    assert "--bg: #f7fbff;" in css
    assert "--panel: #ffffff;" in css
    assert "--signal: #258fd2;" in css
    assert "#356f50" not in css
    assert ".lab-list-item.selected" in css
    assert ".lab-map" in css
    assert "color-scheme: light;" in REPORT_CSS
    assert "--signal: #258fd2;" in REPORT_CSS
    assert "color-scheme: light;" in progress
    assert "#69ddd0" not in progress
    assert "#b9f36a" not in progress
