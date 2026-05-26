"""Analyst updates digests_without_improvement in state.json based on
whether the new digest's best W1 improved over the previous."""
from __future__ import annotations



from efferents.agents.analyst import update_flat_digest_counter


def test_counter_resets_on_improvement():
    state = {"digests_without_improvement": 3, "last_digest_best_w1": 0.020}
    new = update_flat_digest_counter(state, current_best_w1=0.015, epsilon=0.005)
    assert new["digests_without_improvement"] == 0
    assert new["last_digest_best_w1"] == 0.015


def test_counter_increments_on_no_improvement():
    state = {"digests_without_improvement": 1, "last_digest_best_w1": 0.020}
    new = update_flat_digest_counter(state, current_best_w1=0.0205, epsilon=0.005)
    assert new["digests_without_improvement"] == 2


def test_counter_initialized_when_absent():
    state = {}
    new = update_flat_digest_counter(state, current_best_w1=0.020, epsilon=0.005)
    assert new["digests_without_improvement"] == 0
    assert new["last_digest_best_w1"] == 0.020


def test_handles_missing_current_w1():
    state = {"digests_without_improvement": 1, "last_digest_best_w1": 0.020}
    new = update_flat_digest_counter(state, current_best_w1=None, epsilon=0.005)
    # No data → counter unchanged
    assert new["digests_without_improvement"] == 1
