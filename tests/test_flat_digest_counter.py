"""Analyst updates digests_without_improvement in state.json based on
whether the new digest's best headline value improved over the previous."""
from __future__ import annotations



from efferents.agents.analyst import update_flat_digest_counter


def test_counter_resets_on_improvement():
    state = {"digests_without_improvement": 3, "last_digest_best_headline": 0.020}
    new = update_flat_digest_counter(state, current_best_headline=0.015, epsilon=0.005)
    assert new["digests_without_improvement"] == 0
    assert new["last_digest_best_headline"] == 0.015


def test_counter_increments_on_no_improvement():
    state = {"digests_without_improvement": 1, "last_digest_best_headline": 0.020}
    new = update_flat_digest_counter(state, current_best_headline=0.0205, epsilon=0.005)
    assert new["digests_without_improvement"] == 2


def test_counter_initialized_when_absent():
    state = {}
    new = update_flat_digest_counter(state, current_best_headline=0.020, epsilon=0.005)
    assert new["digests_without_improvement"] == 0
    assert new["last_digest_best_headline"] == 0.020


def test_handles_missing_current_headline():
    state = {"digests_without_improvement": 1, "last_digest_best_headline": 0.020}
    new = update_flat_digest_counter(state, current_best_headline=None, epsilon=0.005)
    # No data → counter unchanged
    assert new["digests_without_improvement"] == 1


def test_reads_legacy_last_digest_best_w1():
    # Existing state.json files still carry the old key; it must be honored
    # as the previous value so the counter doesn't spuriously reset.
    state = {"digests_without_improvement": 2, "last_digest_best_w1": 0.020}
    new = update_flat_digest_counter(state, current_best_headline=0.0205, epsilon=0.005)
    assert new["digests_without_improvement"] == 3
    assert new["last_digest_best_headline"] == 0.0205


def test_flat_digest_counter_direction_max():
    from efferents import lab as lab_mod
    from efferents.lab import (Budget, Executor, Headline, LabConfig, Metrics, Source)
    from pathlib import Path
    from efferents.agents.analyst import update_flat_digest_counter
    cfg = LabConfig(lab_id="t", domain="d", pi_handle=None,
        source=Source(dir=Path("/tmp")),
        executor=Executor(run_command="x {config_path}", smoke_command=None, config_template=Path("c.yaml")),
        metrics=Metrics(headline=Headline(column="accuracy", direction="max"), panels=()),
        budget=Budget())
    lab_mod.set_config(cfg)
    try:
        s = {"last_digest_best_headline": 0.80, "digests_without_improvement": 0}
        s2 = update_flat_digest_counter(s, current_best_headline=0.90)  # improved (max)
        assert s2["digests_without_improvement"] == 0
        s3 = update_flat_digest_counter(s2, current_best_headline=0.901)  # within epsilon
        assert s3["digests_without_improvement"] == 1
    finally:
        lab_mod._active = None
