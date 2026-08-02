"""Lab-owned configuration for matched visual evidence comparisons."""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from efferents.lab import LabConfig


def test_from_submission_loads_evidence_comparison(tmp_path):
    source = Path(__file__).parent / "fixtures" / "sample_submission"
    submission = tmp_path / "submission"
    shutil.copytree(source, submission)
    raw = yaml.safe_load((submission / "lab.yaml").read_text())
    raw["evidence"] = {
        "comparison": {
            "axis": "variant",
            "labels": {"qfm": "QFM", "px": "Pixel baseline"},
            "order": ["qfm", "px"],
        }
    }
    (submission / "lab.yaml").write_text(yaml.safe_dump(raw))

    cfg = LabConfig.from_submission(submission)

    assert cfg.evidence.comparison_axis == "variant"
    assert dict(cfg.evidence.comparison_labels) == {
        "qfm": "QFM",
        "px": "Pixel baseline",
    }
    assert cfg.evidence.comparison_order == ("qfm", "px")
