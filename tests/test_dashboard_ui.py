from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "efferents" / "dashboard" / "static"


def test_dashboard_has_connect_steer_observe_entry_flow():
    html = (STATIC / "dashboard.html").read_text()

    assert 'id="connect-form"' in html
    assert 'id="steer-form"' in html
    assert 'data-route-view="observe"' in html
    assert "Connection is non-executing" in html
    assert 'id="runtime-confirm-check"' in html


def test_dashboard_defaults_to_light_with_persistent_dark_opt_in():
    css = (STATIC / "dashboard.css").read_text()
    javascript = (STATIC / "dashboard.js").read_text()

    assert ":root {\n  color-scheme: light;" in css
    assert ':root[data-theme="dark"]' in css
    assert 'localStorage.getItem("efferents-theme")' in javascript
    assert 'stored === "dark" ? "dark" : "light"' in javascript


def test_dark_theme_is_the_inverse_navy_and_white_research_console():
    css = (STATIC / "dashboard.css").read_text()
    dark = css.split(':root[data-theme="dark"] {', 1)[1].split("\n}", 1)[0]

    assert "--bg: #00142f;" in dark
    assert "--panel: #00204d;" in dark
    assert "--panel-raised: #002a61;" in dark
    assert "--line: #ffffff;" in dark
    assert "--fg: #ffffff;" in dark
    assert "--signal: #ffffff;" in dark
    assert "--on-signal: #00204d;" in dark
    assert "--signal-soft: #003b80;" in dark
    assert "--data: #ffffff;" in dark
    assert "#10151c" not in dark
    assert "#8ab2ff" not in dark
    assert "#45c4b0" not in dark
    assert "rgba(10, 16, 26" not in css


def test_dashboard_scripts_are_external_for_strict_script_csp():
    html = (STATIC / "dashboard.html").read_text()

    assert '<script src="/static/dashboard.js"></script>' in html
    assert "<script>" not in html


def test_observe_side_panels_stick_until_replaced_and_can_hide():
    html = (STATIC / "dashboard.html").read_text()
    css = (STATIC / "dashboard.css").read_text()
    javascript = (STATIC / "dashboard.js").read_text()

    assert html.count("data-panel-toggle") == 2
    assert ".side-stack .panel {\n  position: sticky;" in css
    assert ".panel.collapsed .records-list" in css
    assert "initPanelToggles();" in javascript
