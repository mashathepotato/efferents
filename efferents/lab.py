"""Default lab configuration. Override these constants in your own lab.

The framework imports `from efferents import lab` and reads identity +
gating constants from this module. To run a real lab, you have two options:

  (a) Edit this file directly (fine for a single in-repo lab).
  (b) Replace this module by setting up an alias before any
      `efferents.*` import:

          import sys, importlib
          import my_project.lab as my_lab
          sys.modules['efferents.lab'] = my_lab

      Then every `from efferents import lab` resolves to your module.

Future API (planned next session): a `LabConfig` dataclass loaded from a
YAML / Python file at orchestrator startup so users define their lab in
their own repo rather than monkey-patching this module.

A concrete example based on the auto-qml reference lab is kept at
`docs/templates/qml-lab.py.example` for copy-and-modify scaffolding.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Identity — every lab MUST override these.
# ---------------------------------------------------------------------------
LAB_ID: str = "unnamed-lab"
DOMAIN: str = "unspecified"
SUBDOMAIN: str | None = None
PI_HANDLE: str | None = None
CODE_REPO: str = ""


# ---------------------------------------------------------------------------
# Peer-review gate. Applied AFTER the mechanical should_publish gate
# (novelty + significant gain). When enabled, papers enter a 3-reviewer
# board (critical / neutral / enthusiast); only papers with
# mean score ≥ PEER_REVIEW_ACCEPT_MEAN_THRESHOLD and
# min score ≥ PEER_REVIEW_ACCEPT_MIN_THRESHOLD are accepted.
# ---------------------------------------------------------------------------
PEER_REVIEW_ENABLED: bool = False
PEER_REVIEW_ACCEPT_MEAN_THRESHOLD: float = 6.0
PEER_REVIEW_ACCEPT_MIN_THRESHOLD: int = 4


# ---------------------------------------------------------------------------
# Multi-student configuration.
#
# A "student" is a Researcher persona with its own state cursors, backlog,
# popper-corpus subdir, and campaign quota. Different students share the
# same lab (code, kb.sqlite, journal, reviewer board) but pursue
# independent research tracks. The orchestrator round-robins over STUDENTS.
#
# To add a new student: append a dict with id / handle / focus /
# prompt_overrides keys. Existing runs/campaigns are auto-attributed to
# DEFAULT_STUDENT_ID via column defaults; no data migration needed.
# ---------------------------------------------------------------------------
DEFAULT_STUDENT_ID: str = "primary"
MAX_OPEN_CAMPAIGNS_PER_STUDENT: int = 2

STUDENTS: list[dict] = [
    {
        "id": "primary",
        "handle": None,
        "focus": "",
        "prompt_overrides": {},
    },
]


def get_student(student_id: str) -> dict:
    """Look up a student dict by id. Raises KeyError if absent."""
    for s in STUDENTS:
        if s["id"] == student_id:
            return s
    raise KeyError(
        f"unknown student_id={student_id!r}; "
        f"known: {[s['id'] for s in STUDENTS]}"
    )


def student_ids() -> list[str]:
    """All registered student ids, in declaration order. Drives the
    orchestrator round-robin."""
    return [s["id"] for s in STUDENTS]
