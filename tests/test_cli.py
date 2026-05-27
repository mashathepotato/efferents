"""efferents CLI subcommand integration tests."""
from __future__ import annotations
import shutil
from pathlib import Path

import pytest

from efferents.cli import main


SAMPLE = Path(__file__).parent / "fixtures" / "sample_submission"


def test_validate_ok(tmp_path, capsys):
    sub = tmp_path / "sub"
    shutil.copytree(SAMPLE, sub)
    exit_code = main(["validate", "--submission", str(sub)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "OK" in captured.out
    assert "sample-conjecture" in captured.out


def test_validate_missing_submission(tmp_path, capsys):
    exit_code = main(["validate", "--submission", str(tmp_path / "nope")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "hypothesis.md" in captured.err or "hypothesis.md" in captured.out


def test_validate_unknown_subcommand_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == 2  # argparse-style
