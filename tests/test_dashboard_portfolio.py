from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from efferents.dashboard.control import ControlContext


SAMPLE = Path(__file__).parent / "fixtures" / "sample_submission"


def _submission(root: Path, lab_id: str, domain: str) -> Path:
    submission = root / lab_id
    shutil.copytree(SAMPLE, submission)
    (submission / "README.md").write_text(f"# {lab_id}\n")
    raw = yaml.safe_load((submission / "lab.yaml").read_text())
    raw["lab_id"] = lab_id
    raw["domain"] = domain
    (submission / "lab.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    return submission


def test_portfolio_lists_registered_labs_and_switches_without_execution(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    first = _submission(tmp_path, "climate-signal", "climate-science")
    second = _submission(tmp_path, "protein-folding", "computational-biology")
    control = ControlContext()

    control.connect(str(first))
    control.connect(str(second))

    portfolio = control.portfolio()
    assert [lab["lab_id"] for lab in portfolio["labs"]] == [
        "climate-signal",
        "protein-folding",
    ]
    assert portfolio["labs"][1]["selected"] is True
    assert all(lab["visibility"] == "private" for lab in portfolio["labs"])
    assert portfolio["public_network"]["connected"] is False

    selected = control.select_lab("climate-signal")
    assert selected["lab_id"] == "climate-signal"
    assert selected["status"] == "stopped"

    switched = control.portfolio()
    assert [lab["lab_id"] for lab in switched["labs"]] == [
        "climate-signal",
        "protein-folding",
    ]
    assert switched["labs"][0]["selected"] is True
