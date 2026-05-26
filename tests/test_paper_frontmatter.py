"""Paper frontmatter schema (pydantic) + body structural validator."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from efferents.schemas.paper_frontmatter import (
    MetricProvenance,
    PaperFrontmatter,
    REQUIRED_SECTIONS_IN_ORDER,
    structural_check,
)


def _valid_frontmatter_kwargs():
    return dict(
        lab_id="qfm-diffusion",
        domain="quantum-ml",
        subdomain="qfm-diffusion-hep",
        pi_handle="@mashathepotato",
        campaign_id="c-001",
        hypothesis_hash="sha256:" + "0" * 64,
        hypothesis_path="popper-corpus/foo/hypothesis.md",
        metric_provenance=[
            MetricProvenance(
                name="e_w1",
                value=0.012,
                delta_vs_baseline=-0.004,
                runs=["r1", "r2"],
                seeds=[0, 1, 2],
            )
        ],
        novelty_claim="first use of laplacian-pyramid UNet on QFM diffusion",
        published_at="2026-05-17",
        status="preprint",
    )


def test_valid_frontmatter_passes():
    PaperFrontmatter(**_valid_frontmatter_kwargs())


def test_missing_required_field_fails():
    kwargs = _valid_frontmatter_kwargs()
    del kwargs["lab_id"]
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)


def test_code_repo_and_sha_must_both_be_set_or_both_absent():
    kwargs = _valid_frontmatter_kwargs()
    kwargs["code_repo"] = "https://github.com/x/y"
    # code_sha absent → should fail
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)
    kwargs["code_sha"] = "abc1234"
    PaperFrontmatter(**kwargs)  # both set → OK
    kwargs["code_repo"] = None
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)


def test_novelty_claim_nonempty():
    kwargs = _valid_frontmatter_kwargs()
    kwargs["novelty_claim"] = "   "
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)


def test_status_constrained():
    kwargs = _valid_frontmatter_kwargs()
    kwargs["status"] = "published"  # not a Phase-A submission state
    with pytest.raises(ValidationError):
        PaperFrontmatter(**kwargs)


def test_structural_check_accepts_all_five_sections_in_order():
    body = "\n".join(f"## {s}\nSome content.\n" for s in REQUIRED_SECTIONS_IN_ORDER)
    ok, errors = structural_check(body)
    assert ok and errors == []


def test_structural_check_rejects_missing_section():
    sections = REQUIRED_SECTIONS_IN_ORDER[:-1]  # drop "Next questions"
    body = "\n".join(f"## {s}\nSome content.\n" for s in sections)
    ok, errors = structural_check(body)
    assert not ok
    assert any("Next questions" in e for e in errors)


def test_structural_check_rejects_out_of_order():
    reordered = list(REQUIRED_SECTIONS_IN_ORDER)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    body = "\n".join(f"## {s}\nSome content.\n" for s in reordered)
    ok, errors = structural_check(body)
    assert not ok
    assert any("order" in e.lower() for e in errors)
