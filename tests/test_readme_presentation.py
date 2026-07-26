from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]


def test_readme_leads_with_the_interactive_research_workspace():
    readme = (ROOT / "README.md").read_text()

    assert "docs/img/local-lab-workspace.png" in readme
    assert "### Open the local website" in readme
    assert "efferents serve" in readme
    assert "**Connect**" in readme
    assert "**Steer**" in readme
    assert "**Observe**" in readme
    assert "light by default" in readme


def test_readme_workspace_preview_is_a_wide_png():
    preview = (ROOT / "docs/img/local-lab-workspace.png").read_bytes()

    assert preview[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", preview[16:24])
    assert width >= 1200
    assert width / height >= 1.5
