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


# ---------------------------------------------------------------------------
# LabConfig — new per-submission configuration model. Loaded by the daemon
# at startup from <submission>/lab.yaml. Coexists with the legacy module
# constants above; new code reads from `get_config()` instead.
# ---------------------------------------------------------------------------
import re  # noqa: E402  (kept after legacy block)
import yaml  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Literal  # noqa: E402


@dataclass(frozen=True)
class Headline:
    column: str
    direction: Literal["max", "min"]


@dataclass(frozen=True)
class Panel:
    column: str
    label: str
    target: float | None = None


@dataclass(frozen=True)
class Source:
    dir: Path
    allowed_patterns: tuple[str, ...] = ("**/*.py",)


@dataclass(frozen=True)
class Executor:
    run_command: str  # must contain "{config_path}"
    smoke_command: str | None
    config_template: Path
    run_timeout_s: int = 7200
    smoke_timeout_s: int = 300
    env_passthrough: tuple[str, ...] = ()


@dataclass(frozen=True)
class Metrics:
    headline: Headline
    panels: tuple[Panel, ...]
    flat_digest_epsilon: float = 0.005


@dataclass(frozen=True)
class Budget:
    daily_cap_usd: float = 10.0
    sonnet_default: bool = True


class SubmissionError(ValueError):
    """Raised when a submission directory is invalid."""


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_hypothesis(path: Path) -> dict:
    """Parse YAML frontmatter from hypothesis.md and validate the gate."""
    if not path.exists():
        raise SubmissionError(f"hypothesis.md not found at {path}")
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        raise SubmissionError(f"hypothesis.md missing YAML frontmatter at {path}")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise SubmissionError(f"hypothesis.md frontmatter not valid YAML: {e}") from e
    gate = fm.get("falsifiability_gate")
    if gate != "passed":
        raise SubmissionError(
            f"hypothesis.md has falsifiability_gate={gate!r}; expected 'passed'"
        )
    return fm


def _load_lab_yaml(path: Path) -> dict:
    """Load and parse lab.yaml, raising SubmissionError on problems."""
    if not path.exists():
        raise SubmissionError(f"lab.yaml not found at {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise SubmissionError(f"lab.yaml not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise SubmissionError("lab.yaml must be a mapping at top level")
    return data


def _build_labconfig(fm: dict, raw: dict, submission_dir: Path) -> "LabConfig":
    """Construct a LabConfig from parsed hypothesis frontmatter + lab.yaml data."""
    # --- source.dir ---
    src_block = raw.get("source") or {}
    src_dir_str = src_block.get("dir")
    if not src_dir_str:
        raise SubmissionError("lab.yaml: source.dir is required")
    src_dir = (submission_dir / src_dir_str).resolve()
    if not src_dir.is_dir():
        raise SubmissionError(f"source.dir does not exist on disk: {src_dir}")

    # --- executor ---
    exe = raw.get("executor") or {}
    run_command = exe.get("run_command")
    if not run_command:
        raise SubmissionError("lab.yaml: executor.run_command is required")
    if "{config_path}" not in run_command:
        raise SubmissionError(
            "executor.run_command must contain the {config_path} placeholder"
        )
    config_template_str = exe.get("config_template")
    if not config_template_str:
        raise SubmissionError("lab.yaml: executor.config_template is required")
    abs_config_template = (src_dir / config_template_str).resolve()
    if not abs_config_template.is_file():
        raise SubmissionError(
            f"executor.config_template not found under source.dir: {abs_config_template}"
        )

    # --- metrics ---
    metrics_raw = raw.get("metrics") or {}
    headline_raw = metrics_raw.get("headline") or {}
    headline_col = headline_raw.get("column", "")
    if not headline_col:
        raise SubmissionError("lab.yaml: metrics.headline.column is required")
    headline_dir = headline_raw.get("direction")
    if headline_dir not in ("max", "min"):
        raise SubmissionError(
            f"metrics.headline.direction must be 'max' or 'min'; got {headline_dir!r}"
        )

    panels_list = []
    for i, p in enumerate(metrics_raw.get("panels") or []):
        if not isinstance(p, dict) or "column" not in p:
            raise SubmissionError(f"metrics.panels[{i}] missing required 'column' field")
        panels_list.append(Panel(column=p["column"], label=p.get("label", p["column"]), target=p.get("target")))
    panels = tuple(panels_list)

    # --- budget ---
    budget_raw = raw.get("budget") or {}

    # --- lab_id: prefer lab.yaml, fall back to hypothesis slug ---
    lab_id = raw.get("lab_id") or fm.get("slug")
    if not lab_id:
        raise SubmissionError(
            "lab_id missing; provide it in lab.yaml or hypothesis.md slug"
        )

    return LabConfig(
        lab_id=lab_id,
        domain=raw.get("domain", "unspecified"),
        pi_handle=raw.get("pi_handle"),
        source=Source(
            dir=src_dir,
            allowed_patterns=tuple(src_block.get("allowed_patterns") or ("**/*.py",)),
        ),
        executor=Executor(
            run_command=run_command,
            smoke_command=exe.get("smoke_command"),
            config_template=abs_config_template,
            run_timeout_s=int(exe.get("run_timeout_s", 7200)),
            smoke_timeout_s=int(exe.get("smoke_timeout_s", 300)),
            env_passthrough=tuple(exe.get("env_passthrough") or ()),
        ),
        metrics=Metrics(
            headline=Headline(column=headline_col, direction=headline_dir),
            panels=panels,
            flat_digest_epsilon=float(metrics_raw.get("flat_digest_epsilon", 0.005)),
        ),
        budget=Budget(
            daily_cap_usd=float(budget_raw.get("daily_cap_usd", 10.0)),
            sonnet_default=bool(budget_raw.get("sonnet_default", True)),
        ),
    )


@dataclass(frozen=True)
class LabConfig:
    lab_id: str
    domain: str
    pi_handle: str | None
    source: Source
    executor: Executor
    metrics: Metrics
    budget: Budget
    default_student_id: str = "primary"
    max_open_campaigns_per_student: int = 2
    students: tuple[dict, ...] = field(default_factory=lambda: (
        {"id": "primary", "handle": None, "focus": "", "prompt_overrides": {}},
    ))
    peer_review_enabled: bool = False
    peer_review_accept_mean_threshold: float = 6.0
    peer_review_accept_min_threshold: int = 4

    @classmethod
    def from_submission(cls, submission_dir: Path | str) -> "LabConfig":
        """Load a LabConfig from a submission directory.

        The directory must contain:
          - hypothesis.md  (with YAML frontmatter; falsifiability_gate must be 'passed')
          - lab.yaml       (executor, source, metrics configuration)
        """
        submission_dir = Path(submission_dir).resolve()
        fm = _parse_hypothesis(submission_dir / "hypothesis.md")
        raw = _load_lab_yaml(submission_dir / "lab.yaml")
        return _build_labconfig(fm, raw, submission_dir)


# ---------------------------------------------------------------------------
# Active-config accessors and legacy-constant shim helper.
# ---------------------------------------------------------------------------
_active: LabConfig | None = None


def set_config(cfg: LabConfig) -> None:
    """Install the active LabConfig. Called by the daemon at startup."""
    global _active
    _active = cfg


def get_config() -> LabConfig:
    """Return the active LabConfig or raise RuntimeError."""
    if _active is None:
        raise RuntimeError(
            "LabConfig not loaded; call set_config() before agent code runs"
        )
    return _active


def _labconfig_attr_via_shim(name: str):
    """Resolve a legacy module-level constant from the active LabConfig.
    Used by the PEP 562 __getattr__ once the static constants are removed."""
    cfg = get_config()
    mapping = {
        "LAB_ID": cfg.lab_id,
        "DOMAIN": cfg.domain,
        "SUBDOMAIN": None,
        "PI_HANDLE": cfg.pi_handle,
        "CODE_REPO": "",
        "DEFAULT_STUDENT_ID": cfg.default_student_id,
        "MAX_OPEN_CAMPAIGNS_PER_STUDENT": cfg.max_open_campaigns_per_student,
        "STUDENTS": list(cfg.students),
        "PEER_REVIEW_ENABLED": cfg.peer_review_enabled,
        "PEER_REVIEW_ACCEPT_MEAN_THRESHOLD": cfg.peer_review_accept_mean_threshold,
        "PEER_REVIEW_ACCEPT_MIN_THRESHOLD": cfg.peer_review_accept_min_threshold,
    }
    if name not in mapping:
        raise AttributeError(name)
    return mapping[name]
