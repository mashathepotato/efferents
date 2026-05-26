"""Writer emits valid frontmatter + the five required body sections."""
from __future__ import annotations

import yaml

import pytest

from efferents.agents.writer import compose_paper
from efferents.schemas.paper_frontmatter import (
    PaperFrontmatter,
    REQUIRED_SECTIONS_IN_ORDER,
    structural_check,
)


def test_compose_paper_returns_valid_artifact(fake_anthropic_factory):
    body_md = "\n".join(
        f"## {s}\n\nSome content for {s}.\n" for s in REQUIRED_SECTIONS_IN_ORDER
    )
    client = fake_anthropic_factory([body_md])
    artifact = compose_paper(
        client=client,
        campaign={
            "id": "c-1",
            "question": "does X help?",
            "hypothesis_path": "popper-corpus/c1/hypothesis.md",
            "hypothesis_hash": "sha256:" + "0" * 64,
        },
        metric_provenance=[
            {
                "name": "e_w1",
                "value": 0.012,
                "delta_vs_baseline": -0.004,
                "runs": ["r1"],
                "seeds": [0, 1, 2],
            }
        ],
        novelty_claim="first lap-pyr UNet on QFM",
        code_sha="abcdef1",
        code_repo="https://github.com/mashathepotato/auto-qml",
    )
    assert artifact.startswith("---")
    _, fm_yaml, body = artifact.split("---", 2)
    fm = yaml.safe_load(fm_yaml)
    PaperFrontmatter(**fm)  # raises on invalid
    ok, errors = structural_check(body)
    assert ok, errors


def test_compose_paper_fails_loud_when_body_missing_section(fake_anthropic_factory):
    bad_body = "## Motivation\n\nfoo\n\n## Results\n\nbar\n"
    client = fake_anthropic_factory([bad_body])
    with pytest.raises(ValueError, match="missing required section"):
        compose_paper(
            client=client,
            campaign={
                "id": "c-1",
                "question": "q",
                "hypothesis_path": "popper-corpus/c1/hypothesis.md",
                "hypothesis_hash": "sha256:" + "0" * 64,
            },
            metric_provenance=[
                {
                    "name": "e_w1",
                    "value": 0.012,
                    "delta_vs_baseline": -0.004,
                    "runs": ["r1"],
                    "seeds": [0],
                }
            ],
            novelty_claim="x",
            code_sha=None,
            code_repo=None,
        )


def test_compose_paper_allows_omitted_code_pointers(fake_anthropic_factory):
    body_md = "\n".join(
        f"## {s}\n\nContent.\n" for s in REQUIRED_SECTIONS_IN_ORDER
    )
    client = fake_anthropic_factory([body_md])
    artifact = compose_paper(
        client=client,
        campaign={
            "id": "c-1",
            "question": "q",
            "hypothesis_path": "popper-corpus/c1/hypothesis.md",
            "hypothesis_hash": "sha256:" + "0" * 64,
        },
        metric_provenance=[
            {"name": "e_w1", "value": 0.012, "delta_vs_baseline": -0.004,
             "runs": ["r1"], "seeds": [0]},
        ],
        novelty_claim="prose-only artifact",
        code_sha=None,
        code_repo=None,
    )
    _, fm_yaml, _ = artifact.split("---", 2)
    fm = yaml.safe_load(fm_yaml)
    assert fm["code_repo"] is None and fm["code_sha"] is None
