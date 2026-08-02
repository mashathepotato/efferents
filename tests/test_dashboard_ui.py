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
