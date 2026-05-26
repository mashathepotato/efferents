"""popper_gate.run runs single-shot self-play and validates output."""
from __future__ import annotations

from pathlib import Path

import pytest

from efferents.agents.popper_gate import GateResult, run_gate


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def popper_repo(monkeypatch, tmp_path):
    """Build a minimal popper-probe-shaped directory with the canonical
    SKILL.md and validate_hypothesis.py so the gate can find them without
    depending on the user's working copy."""
    repo = tmp_path / "popper-probe"
    (repo / "skills" / "intake").mkdir(parents=True)
    (repo / "scripts").mkdir()
    real_skill = Path.home() / "Documents/popper-probe/skills/intake/SKILL.md"
    real_validator = Path.home() / "Documents/popper-probe/scripts/validate_hypothesis.py"
    skill_dst = repo / "skills/intake/SKILL.md"
    if real_skill.exists():
        skill_dst.write_text(real_skill.read_text())
    else:
        skill_dst.write_text("# Stub SKILL.md\n")
    if real_validator.exists():
        (repo / "scripts/validate_hypothesis.py").write_text(real_validator.read_text())
    else:
        pytest.skip("Real popper-probe validate_hypothesis.py not available")
    monkeypatch.setenv("POPPER_PROBE_REPO", str(repo))
    return repo


def test_accept_path_writes_file_and_returns_hash(
    popper_repo, tmp_path, fake_anthropic_factory
):
    valid_text = (FIXTURES / "valid_hypothesis.md").read_text()
    client = fake_anthropic_factory([valid_text])
    out_root = tmp_path / "popper-corpus"

    result = run_gate(
        draft_claim="aug_depth=3 should reduce W1 by 10%",
        slug="aug-depth-three",
        corpus_root=out_root,
        client=client,
    )

    assert isinstance(result, GateResult)
    assert result.ok
    assert result.path == out_root / "aug-depth-three/hypothesis.md"
    assert result.path.exists()
    assert result.path.read_text() == valid_text
    assert result.hash.startswith("sha256:")
    assert len(result.hash) == len("sha256:") + 64


def test_reject_then_drop_after_one_retry(
    popper_repo, tmp_path, fake_anthropic_factory
):
    invalid_text = (FIXTURES / "invalid_hypothesis.md").read_text()
    client = fake_anthropic_factory([invalid_text, invalid_text])
    out_root = tmp_path / "popper-corpus"

    result = run_gate(
        draft_claim="something fuzzy",
        slug="fuzzy",
        corpus_root=out_root,
        client=client,
    )

    assert not result.ok
    assert result.reason
    assert "validate" in result.reason.lower() or "schema" in result.reason.lower()
    # The model was retried once → 2 calls total
    assert len(client.calls) == 2


def test_retry_succeeds(popper_repo, tmp_path, fake_anthropic_factory):
    invalid_text = (FIXTURES / "invalid_hypothesis.md").read_text()
    valid_text = (FIXTURES / "valid_hypothesis.md").read_text()
    client = fake_anthropic_factory([invalid_text, valid_text])
    out_root = tmp_path / "popper-corpus"

    result = run_gate(
        draft_claim="retry case",
        slug="retry-case",
        corpus_root=out_root,
        client=client,
    )

    assert result.ok
    assert len(client.calls) == 2
    # On retry, the user message must include the validator's errors so the
    # model can correct course
    second_user_msgs = client.calls[1].get("messages", [])
    assert any("ERROR" in str(m) or "validator" in str(m).lower() for m in second_user_msgs)
