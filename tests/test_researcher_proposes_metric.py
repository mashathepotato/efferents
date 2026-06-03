from efferents.agents.researcher import _campaign_metric_from_proposal


def test_valid_metric_passes_through():
    nc = {"headline_metric": "synthetic_loss", "direction": "min"}
    assert _campaign_metric_from_proposal(nc) == ("synthetic_loss", "min")


def test_invalid_metric_name_drops_to_none():
    nc = {"headline_metric": "bad name!", "direction": "min"}
    assert _campaign_metric_from_proposal(nc) == (None, None)


def test_bad_direction_drops_to_none():
    nc = {"headline_metric": "loss", "direction": "sideways"}
    assert _campaign_metric_from_proposal(nc) == (None, None)


def test_missing_metric_is_none():
    assert _campaign_metric_from_proposal({}) == (None, None)
