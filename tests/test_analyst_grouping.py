"""Analyst groups recent runs by campaign_id for the digest prompt."""
from __future__ import annotations


from efferents.agents.analyst import group_runs_by_campaign


def test_groups_runs_with_campaign_id():
    runs = [
        {"run_id": "r1", "campaign_id": "c1", "e_w1": 0.02},
        {"run_id": "r2", "campaign_id": "c1", "e_w1": 0.01},
        {"run_id": "r3", "campaign_id": "c2", "e_w1": 0.03},
    ]
    grouped = group_runs_by_campaign(runs)
    assert set(grouped.keys()) == {"c1", "c2"}
    assert len(grouped["c1"]) == 2
    assert len(grouped["c2"]) == 1


def test_runs_without_campaign_under_none_key():
    runs = [
        {"run_id": "r1", "campaign_id": None, "e_w1": 0.02},
        {"run_id": "r2", "campaign_id": "c1", "e_w1": 0.01},
    ]
    grouped = group_runs_by_campaign(runs)
    assert None in grouped
    assert len(grouped[None]) == 1


def test_empty_input():
    assert group_runs_by_campaign([]) == {}
