"""Framework prompts must carry no QML-specific vocabulary."""
from __future__ import annotations
import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "efferents" / "agents" / "prompts"
QML_TOKENS = re.compile(
    r"e_w1|raw_q|aug_depth|active_frac|radial_l2|qfm|jet|amp_ratio|wallpaper|auto_qml|gen_max",
    re.IGNORECASE,
)


def test_no_qml_tokens_in_framework_prompts():
    offenders = {}
    for md in sorted(PROMPTS_DIR.glob("*.md")):
        hits = QML_TOKENS.findall(md.read_text())
        if hits:
            offenders[md.name] = sorted(set(h.lower() for h in hits))
    assert not offenders, f"QML tokens found in framework prompts: {offenders}"
