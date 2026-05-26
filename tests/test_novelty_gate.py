"""The Writer is only triggered when a campaign shows novelty + significant gain."""
from __future__ import annotations


from efferents.agents.writer import should_publish, GateInputs


def test_below_threshold_blocks():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.0199,   # only 0.5% better
        novelty_claim="some claim",
        existing_lab_claims=[],
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert not ok
    assert "gain" in reason.lower()


def test_at_threshold_passes():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.018,   # 10% better
        novelty_claim="first lap-pyr UNet on QFM",
        existing_lab_claims=["amp-ratio gate", "annular radial head"],
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert ok, reason


def test_empty_novelty_blocks():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.010,
        novelty_claim="   ",
        existing_lab_claims=[],
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert not ok
    assert "novel" in reason.lower()


def test_duplicates_existing_claim_blocks():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.010,
        novelty_claim="amp-ratio gate",
        existing_lab_claims=["amp-ratio gate", "annular radial head"],
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert not ok
    assert "duplicate" in reason.lower() or "existing" in reason.lower()


def test_refutation_path_passes_without_gain():
    inputs = GateInputs(
        primary_metric_name="e_w1",
        baseline_value=0.020,
        candidate_value=0.020,   # no gain
        novelty_claim="refutes prior corroborated claim X",
        existing_lab_claims=[],
        refutation_of_corroborated="claim-x",
    )
    ok, reason = should_publish(inputs, gain_threshold=0.05)
    assert ok
