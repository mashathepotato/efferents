from pathlib import Path

from efferents.journal.feed import FeedCard, render_feed

VALID_PAPER = """---
lab_id: smoke-coefficient
domain: synthetic
campaign_id: camp-1
hypothesis_hash: "sha256:{h}"
hypothesis_path: popper-corpus/x/hypothesis.md
metric_provenance:
  - name: synthetic_loss
    value: 0.031
    runs: ["a3f1"]
    seeds: [0]
novelty_claim: Coefficient near 0.79 minimizes synthetic loss.
published_at: 2026-06-09
status: preprint
---

# Optimal coefficient for synthetic loss

## Motivation
Body text.
""".format(h="0" * 64)


def _write(p: Path, text: str) -> Path:
    p.write_text(text)
    return p


def test_render_feed_parses_valid_paper(tmp_path):
    paper = _write(tmp_path / "camp-1.md", VALID_PAPER)
    cards = render_feed([paper])
    assert len(cards) == 1
    card = cards[0]
    assert isinstance(card, FeedCard)
    assert card.lab_id == "smoke-coefficient"
    assert card.campaign_id == "camp-1"
    assert card.title == "Optimal coefficient for synthetic loss"
    assert card.summary == "Coefficient near 0.79 minimizes synthetic loss."
    assert card.status == "preprint"
    assert card.published_at == "2026-06-09"


def test_render_feed_sorts_newest_first(tmp_path):
    older = VALID_PAPER.replace("2026-06-09", "2026-06-01").replace("camp-1", "camp-old")
    newer = VALID_PAPER.replace("2026-06-09", "2026-06-10").replace("camp-1", "camp-new")
    p_old = _write(tmp_path / "camp-old.md", older)
    p_new = _write(tmp_path / "camp-new.md", newer)
    cards = render_feed([p_old, p_new])
    assert [c.campaign_id for c in cards] == ["camp-new", "camp-old"]


def test_render_feed_skips_malformed(tmp_path):
    bad = _write(tmp_path / "bad.md", "no frontmatter here")
    missing = _write(tmp_path / "missing.md", "---\nlab_id: x\n---\n\nbody")
    good = _write(tmp_path / "camp-1.md", VALID_PAPER)
    cards = render_feed([bad, missing, good])
    assert [c.campaign_id for c in cards] == ["camp-1"]


def test_render_feed_title_falls_back_to_novelty_claim(tmp_path):
    no_heading = VALID_PAPER.replace("# Optimal coefficient for synthetic loss\n\n", "")
    paper = _write(tmp_path / "camp-1.md", no_heading)
    cards = render_feed([paper])
    assert cards[0].title == "Coefficient near 0.79 minimizes synthetic loss."


def test_render_feed_skips_unreadable_path(tmp_path):
    good = _write(tmp_path / "camp-1.md", VALID_PAPER)
    missing_path = tmp_path / "does-not-exist.md"
    cards = render_feed([missing_path, good])
    assert [c.campaign_id for c in cards] == ["camp-1"]
