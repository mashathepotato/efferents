"""efferents CLI subcommand integration tests."""
from __future__ import annotations
import os
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


def test_start_foreground_registers_and_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    sub = tmp_path / "sub"
    shutil.copytree(SAMPLE, sub)

    called = []
    def fake_loop():
        called.append(1)
    monkeypatch.setattr("efferents.cli._orchestrator_loop", fake_loop)

    exit_code = main(["start", "--submission", str(sub)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "lab_id=sample-conjecture" in captured.out
    assert called == [1]

    from efferents.registry import Registry
    rec = Registry().get("sample-conjecture")
    assert rec is not None
    assert rec.lab_id == "sample-conjecture"


def test_start_detach_writes_pidfile(tmp_path, monkeypatch):
    """Detach path forks; we test the post-fork bookkeeping via a stubbed daemonize call."""
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    sub = tmp_path / "sub"
    shutil.copytree(SAMPLE, sub)

    fake_child_pid = 4242
    def fake_daemonize(lab_root, loop):
        return fake_child_pid
    monkeypatch.setattr("efferents.cli.daemon.daemonize_and_run", fake_daemonize)

    exit_code = main(["start", "--submission", str(sub), "--detach"])
    assert exit_code == 0

    from efferents.registry import Registry
    rec = Registry().get("sample-conjecture")
    assert rec is not None
    assert rec.pid == fake_child_pid


def test_status_running_lab(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    from efferents.registry import LabRecord, Registry
    reg = Registry()
    reg.register(LabRecord(
        lab_id="x", submission_dir=str(tmp_path / "s"),
        lab_root=str(tmp_path / "s/lab"), pid=os.getpid(),
        started_at="2026-05-26T10:00:00Z", status="running",
    ))
    (tmp_path / "s" / "lab").mkdir(parents=True)
    (tmp_path / "s" / "lab" / "state.json").write_text("{}")

    exit_code = main(["status", "--lab-id", "x"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "running" in captured.out
    assert "x" in captured.out


def test_status_dead_pid_marks_crashed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    from efferents.registry import LabRecord, Registry
    reg = Registry()
    reg.register(LabRecord(
        lab_id="y", submission_dir=str(tmp_path / "s"),
        lab_root=str(tmp_path / "s/lab"), pid=999999,
        started_at="2026-05-26T10:00:00Z", status="running",
    ))

    exit_code = main(["status", "--lab-id", "y"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "crashed" in captured.out.lower() or "dead" in captured.out.lower()


def test_status_unknown_lab(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    exit_code = main(["status", "--lab-id", "nope"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "not found" in captured.err.lower() or "unknown" in captured.err.lower()


def test_stop_marks_registry_stopped(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    from efferents.registry import LabRecord, Registry
    reg = Registry()
    reg.register(LabRecord(
        lab_id="z", submission_dir="/x", lab_root="/x/lab",
        pid=999999, started_at="t", status="running",
    ))

    monkeypatch.setattr("efferents.cli.os.kill", lambda pid, sig: None)
    monkeypatch.setattr("efferents.cli.daemon.is_pid_alive", lambda pid: False)

    exit_code = main(["stop", "--lab-id", "z"])
    assert exit_code == 0
    assert reg.get("z").status == "stopped"


def test_stop_unknown_lab(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    exit_code = main(["stop", "--lab-id", "ghost"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "unknown" in captured.err.lower() or "not found" in captured.err.lower()


def test_list_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    exit_code = main(["list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "no labs registered" in captured.out.lower() or "LAB_ID" in captured.out


def test_list_with_entries(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    from efferents.registry import LabRecord, Registry
    reg = Registry()
    reg.register(LabRecord(
        lab_id="alpha", submission_dir="/a", lab_root="/a/lab",
        pid=os.getpid(), started_at="2026-05-26T10:00:00Z", status="running",
    ))
    reg.register(LabRecord(
        lab_id="beta", submission_dir="/b", lab_root="/b/lab",
        pid=999999, started_at="2026-05-25T10:00:00Z", status="running",
    ))
    exit_code = main(["list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "alpha" in captured.out
    assert "beta" in captured.out
