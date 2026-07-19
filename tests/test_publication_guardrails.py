from __future__ import annotations

import json
import subprocess
from pathlib import Path

from efferents.cli import main
from efferents.publication import (
    check_public_repository,
    format_publication_report,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path, *, with_license: bool = True) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "guardrails@example.test")
    _git(repo, "config", "user.name", "Guardrail Test")
    (repo / "README.md").write_text("# publishable test repository\n")
    if with_license:
        (repo / "LICENSE").write_text("Test licence terms for redistribution.\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "initial")
    return repo


def test_clean_repository_requires_named_manual_review(tmp_path):
    repo = _init_repo(tmp_path)

    first = check_public_repository(repo)
    approved = check_public_repository(repo, reviewer="A. Reviewer")

    assert first.status == "needs_manual_review"
    assert approved.status == "ready"
    assert approved.reviewer == "A. Reviewer"
    assert not approved.blockers


def test_missing_repository_license_blocks_publication(tmp_path):
    repo = _init_repo(tmp_path, with_license=False)

    report = check_public_repository(repo, reviewer="A. Reviewer")

    assert report.status == "blocked"
    assert any(f.code == "LICENSE_MISSING" for f in report.blockers)


def test_current_secret_is_blocked_and_redacted_from_reports(tmp_path):
    repo = _init_repo(tmp_path)
    leaked = "ghp_" + "A" * 40
    (repo / "config.py").write_text(f'TOKEN = "{leaked}"\n')
    _git(repo, "add", "config.py")
    _git(repo, "commit", "-qm", "add config")

    report = check_public_repository(repo, reviewer="Security Reviewer")
    rendered = format_publication_report(report)
    payload = report.to_json()

    assert report.status == "blocked"
    assert any(f.code == "SECRET_GITHUB_TOKEN" for f in report.blockers)
    assert leaked not in rendered
    assert leaked not in payload


def test_secret_removed_from_head_still_blocks_when_present_in_history(tmp_path):
    repo = _init_repo(tmp_path)
    leaked = "sk-ant-" + "B" * 32
    secret_path = repo / "old_config.py"
    secret_path.write_text(f'API_KEY = "{leaked}"\n')
    _git(repo, "add", "old_config.py")
    _git(repo, "commit", "-qm", "temporarily add secret")
    secret_path.unlink()
    _git(repo, "add", "-u")
    _git(repo, "commit", "-qm", "remove secret")

    report = check_public_repository(repo, reviewer="Security Reviewer")

    assert report.status == "blocked"
    assert any(f.code == "HISTORY_SECRET_ANTHROPIC_KEY" for f in report.blockers)
    assert leaked not in report.to_json()


def test_media_artifact_requires_review_but_can_be_attested(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00")
    _git(repo, "add", "figure.png")
    _git(repo, "commit", "-qm", "add figure")

    report = check_public_repository(repo, reviewer="Rights Reviewer")

    assert report.status == "ready"
    assert any(f.code == "MEDIA_ARTIFACT" for f in report.review_items)


def test_dirty_worktree_blocks_exact_release_attestation(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "untracked.txt").write_text("not part of the reviewed commit\n")

    report = check_public_repository(repo, reviewer="A. Reviewer")

    assert any(f.code == "GIT_DIRTY" for f in report.blockers)
    assert report.status == "blocked"


def test_skipping_history_cannot_clear_a_public_release(tmp_path):
    repo = _init_repo(tmp_path)

    report = check_public_repository(
        repo, reviewer="A. Reviewer", scan_history=False
    )

    assert any(f.code == "HISTORY_SCAN_SKIPPED" for f in report.blockers)
    assert report.status == "blocked"


def test_public_check_cli_writes_auditable_json_report(tmp_path, capsys):
    repo = _init_repo(tmp_path)
    report_path = tmp_path / "publication-report.json"

    exit_code = main([
        "public-check",
        str(repo),
        "--acknowledge-manual-review",
        "Masha Reviewer",
        "--report",
        str(report_path),
    ])
    captured = capsys.readouterr()
    payload = json.loads(report_path.read_text())

    assert exit_code == 0
    assert "PUBLIC RELEASE CHECK: READY" in captured.out
    assert payload["status"] == "ready"
    assert payload["reviewer"] == "Masha Reviewer"
    assert payload["history_scanned"] is True
