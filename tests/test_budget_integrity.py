from __future__ import annotations

import json
import subprocess

from efferents.agents.budget import BudgetTracker, CallUsage
from efferents.agents.journal import auto_commit_paper


def test_budget_record_includes_external_tool_cost(tmp_path):
    tracker = BudgetTracker(tmp_path / "budget.jsonl", daily_cap_usd=1.0)

    record = tracker.record(
        agent="librarian",
        model="claude-sonnet-4-6",
        usage=CallUsage(input_tokens=1000, output_tokens=100),
        extra_cost_usd=0.03,
        notes="three searches",
    )

    assert record["cost_usd"] == record["token_cost_usd"] + 0.03
    persisted = json.loads((tmp_path / "budget.jsonl").read_text())
    assert persisted["extra_cost_usd"] == 0.03
    assert tracker.spend_total() == record["cost_usd"]


def test_paper_commit_refuses_pre_staged_user_changes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Writer Test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "writer@example.invalid"], cwd=repo, check=True
    )
    user_file = repo / "user.txt"
    user_file.write_text("initial\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=repo, check=True)
    user_file.write_text("user staged work\n")
    subprocess.run(["git", "add", "user.txt"], cwd=repo, check=True)

    sha = auto_commit_paper(
        repo_root=repo,
        campaign_id="c1",
        headline="result",
        decision={"mean_score": 7, "min_score": 6},
    )

    assert sha is None
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert staged == ["user.txt"]
