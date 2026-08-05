from pathlib import Path
import runpy

import pytest

from efferents.dashboard.charts import CHARTS_JS, CHARTS_JS_MARKER, embed_charts
from efferents.repo_adapter import RepoAdapterConfig


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "examples" / "challengescape" / "live.py"
LAB_01 = ROOT / "examples" / "challengescape" / "labs" / "lab_01_reasoning_verification"


def test_chart_runtime_is_registry_based_and_responsive():
    assert "EfferentsCharts" in CHARTS_JS
    assert "register" in CHARTS_JS
    assert "specsFromRuns" in CHARTS_JS
    for built_in in ('register("line"', 'register("bar"', 'register("spark"'):
        assert built_in in CHARTS_JS
    # Charts re-render at the container's measured width — never a fixed-width
    # SVG scaled down by max-width.
    assert "clientWidth" in CHARTS_JS
    assert "ResizeObserver" in CHARTS_JS


def test_charts_embedding_requires_marker():
    with pytest.raises(ValueError, match="exactly one"):
        embed_charts("<html></html>")
    assert CHARTS_JS in embed_charts(f"<script>{CHARTS_JS_MARKER}</script>")


def test_live_workspace_uses_chart_runtime_not_bespoke_svg():
    page = runpy.run_path(str(LIVE))["PAGE"]

    assert "EfferentsCharts" in page
    assert CHARTS_JS_MARKER not in page
    assert "data-chartset" in page
    assert "chart(lab, color, 430, 210)" not in page


def test_lab_charts_config_is_first_class():
    cfg = RepoAdapterConfig.load(LAB_01)

    assert cfg.charts, "example lab should declare workspace charts"
    first = cfg.charts[0]
    assert first.metric == "clean_fa_drop_k1_to_k3"
    assert first.target == pytest.approx(0.20)
    assert any(chart.type == "bar" for chart in cfg.charts)


def test_charts_config_validation():
    base = {
        "goal": "g",
        "train_command": "t {config_path}",
        "eval_command": "e {checkpoint}",
        "metric": "m",
    }
    with pytest.raises(ValueError, match="charts"):
        RepoAdapterConfig.from_dict({**base, "charts": "nope"})
    with pytest.raises(ValueError, match="metric"):
        RepoAdapterConfig.from_dict({**base, "charts": [{"type": "line"}]})
