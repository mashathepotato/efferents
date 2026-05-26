"""Mode selector heuristic + force_mode override from research_log.md."""
from __future__ import annotations



from efferents.agents.orchestrator import select_mode, read_force_mode


def _state(flat_digests=0):
    return {"digests_without_improvement": flat_digests}


def test_refine_when_no_flat_digests():
    assert select_mode(_state(0), override=None) == "refine"


def test_moonshot_at_two_flat_digests():
    assert select_mode(_state(2), override=None) == "moonshot"


def test_devils_advocate_at_three():
    assert select_mode(_state(3), override=None) == "devils_advocate"


def test_escape_to_code_at_four():
    assert select_mode(_state(4), override=None) == "escape_to_code"


def test_override_wins(tmp_path):
    assert select_mode(_state(0), override="moonshot") == "moonshot"


def test_unknown_override_falls_back(tmp_path):
    assert select_mode(_state(0), override="banana") == "refine"


def test_read_force_mode_returns_value(tmp_path):
    log = tmp_path / "research_log.md"
    log.write_text("Some narrative.\n\nforce_mode: devils_advocate\n\nMore narrative.\n")
    assert read_force_mode(tmp_path) == "devils_advocate"


def test_read_force_mode_returns_none_when_absent(tmp_path):
    log = tmp_path / "research_log.md"
    log.write_text("No directive here.\n")
    assert read_force_mode(tmp_path) is None


def test_read_force_mode_uses_last_occurrence(tmp_path):
    log = tmp_path / "research_log.md"
    log.write_text(
        "force_mode: moonshot\n\nsome notes\n\nforce_mode: refine\n"
    )
    assert read_force_mode(tmp_path) == "refine"
