"""~/.efferents/registry.json read/write with file lock."""
from __future__ import annotations
import json
import os
from pathlib import Path

import pytest

from efferents.registry import LabRecord, Registry


def test_registry_empty_on_first_read(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    assert reg.list() == []


def test_register_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    rec = LabRecord(
        lab_id="my-lab",
        submission_dir=str(tmp_path / "sub"),
        lab_root=str(tmp_path / "sub/lab"),
        pid=12345,
        started_at="2026-05-26T14:02:00Z",
        status="running",
    )
    reg.register(rec)
    listed = reg.list()
    assert len(listed) == 1
    assert listed[0].lab_id == "my-lab"
    assert listed[0].pid == 12345


def test_register_idempotent_on_lab_id(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    rec1 = LabRecord(lab_id="x", submission_dir="/a", lab_root="/a/lab",
                     pid=1, started_at="t1", status="running")
    rec2 = LabRecord(lab_id="x", submission_dir="/a", lab_root="/a/lab",
                     pid=2, started_at="t2", status="running")
    reg.register(rec1)
    reg.register(rec2)
    listed = reg.list()
    assert len(listed) == 1
    assert listed[0].pid == 2  # latest wins


def test_get_by_lab_id(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    reg.register(LabRecord(lab_id="y", submission_dir="/b", lab_root="/b/lab",
                           pid=99, started_at="t", status="running"))
    rec = reg.get("y")
    assert rec is not None
    assert rec.pid == 99
    assert reg.get("nonexistent") is None


def test_update_status(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    reg.register(LabRecord(lab_id="z", submission_dir="/c", lab_root="/c/lab",
                           pid=5, started_at="t", status="running"))
    reg.update_status("z", "stopped")
    assert reg.get("z").status == "stopped"


def test_corrupted_json_recovered(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg_path = tmp_path / "registry.json"
    reg_path.write_text("{not valid json")
    reg = Registry()
    assert reg.list() == []
