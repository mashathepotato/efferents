from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_STUDENT_MD = _REPO_ROOT / "efferents" / "agents" / "prompts" / "student.md"


def test_new_campaign_example_lists_metric_fields():
    text = _STUDENT_MD.read_text()
    assert "headline_metric" in text
    assert "direction" in text
    # The example object (not just prose) must mention headline_metric so
    # the model actually emits it. Heuristic: the LAST occurrence of
    # draft_hypothesis is the one inside the code-fence example block
    # (earlier occurrences are in prose); headline_metric should appear
    # within 400 chars after that (i.e. inside the same example block).
    idx_draft = text.rindex("draft_hypothesis")
    assert "headline_metric" in text[idx_draft: idx_draft + 400]
