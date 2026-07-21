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

A concrete example lab module (modeled on the reference lab) is kept at
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
PEER_REVIEW_GAIN_THRESHOLD: float = 0.05
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
    direction: Literal["max", "min"] = "min"


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
    # Run columns that define an "experimental axis" for saturation analysis
    # (the Researcher groups runs by these before checking whether a metric has
    # stalled). Empty means treat all runs as a single bucket.
    bucket_axes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Budget:
    daily_cap_usd: float = 10.0
    sonnet_default: bool = True


@dataclass(frozen=True)
class Autonomy:
    """Mutation controls for a live lab.

    The Coder is intentionally opt-in. Experiment execution is already
    authorized by the lab's run command; source-code mutation is a materially
    different permission and must never be inferred from that.
    """

    coder_enabled: bool = False


class SubmissionError(ValueError):
    """Raised when a submission directory is invalid."""


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_COL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def _build_labconfig(
    fm: dict, raw: dict, submission_dir: Path, check_paths: bool = True
) -> "LabConfig":
    """Construct a LabConfig from parsed hypothesis frontmatter + lab.yaml data.

    ``check_paths=False`` skips existence checks for source.dir and
    config_template.  Use this when loading config for read-only purposes (e.g.
    the dashboard serve command) where the source tree may be rooted elsewhere.
    """
    # --- source.dir ---
    src_block = raw.get("source") or {}
    src_dir_str = src_block.get("dir")
    if not src_dir_str:
        raise SubmissionError("lab.yaml: source.dir is required")
    src_dir = (submission_dir / src_dir_str).resolve()
    try:
        src_dir.relative_to(submission_dir.resolve())
    except ValueError as e:
        raise SubmissionError(
            f"source.dir must stay inside the submission directory: {src_dir}"
        ) from e
    if check_paths and not src_dir.is_dir():
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
    try:
        abs_config_template.relative_to(submission_dir.resolve())
    except ValueError as e:
        raise SubmissionError(
            "executor.config_template must stay inside the submission directory"
        ) from e
    if check_paths and not abs_config_template.is_file():
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
    if not _COL_NAME_RE.match(headline_col):
        raise SubmissionError(
            f"metrics.headline.column {headline_col!r} must match [A-Za-z_][A-Za-z0-9_]* "
            f"(SQL identifier rules)"
        )

    panels_list = []
    for i, p in enumerate(metrics_raw.get("panels") or []):
        if not isinstance(p, dict) or "column" not in p:
            raise SubmissionError(f"metrics.panels[{i}] missing required 'column' field")
        if not _COL_NAME_RE.match(p["column"]):
            raise SubmissionError(
                f"metrics.panels[{i}].column {p['column']!r} must match "
                f"[A-Za-z_][A-Za-z0-9_]* (SQL identifier rules)"
            )
        panel_dir = p.get("direction", "min")
        if panel_dir not in ("max", "min"):
            raise SubmissionError(
                f"metrics.panels[{i}].direction must be 'max' or 'min'; got {panel_dir!r}"
            )
        panels_list.append(Panel(
            column=p["column"], label=p.get("label", p["column"]),
            target=p.get("target"), direction=panel_dir,
        ))
    panels = tuple(panels_list)

    bucket_axes_raw = metrics_raw.get("bucket_axes") or ()
    for i, ax in enumerate(bucket_axes_raw):
        if not isinstance(ax, str) or not _COL_NAME_RE.match(ax):
            raise SubmissionError(
                f"metrics.bucket_axes[{i}] {ax!r} must match "
                f"[A-Za-z_][A-Za-z0-9_]* (SQL identifier rules)"
            )
    bucket_axes = tuple(bucket_axes_raw)

    # --- budget / autonomy / peer review / students ---
    budget_raw = raw.get("budget") or {}
    autonomy_raw = raw.get("autonomy") or {}
    peer_review_raw = raw.get("peer_review") or {}

    students_raw = raw.get("students")
    if students_raw is None:
        students = (
            {"id": "primary", "handle": None, "focus": "", "prompt_overrides": {}},
        )
    else:
        if not isinstance(students_raw, list) or not students_raw:
            raise SubmissionError("lab.yaml: students must be a non-empty list")
        parsed_students: list[dict] = []
        seen_student_ids: set[str] = set()
        for i, student in enumerate(students_raw):
            if not isinstance(student, dict):
                raise SubmissionError(f"students[{i}] must be a mapping")
            student_id = student.get("id")
            if not isinstance(student_id, str) or not re.fullmatch(
                r"[a-z][a-z0-9_-]*", student_id
            ):
                raise SubmissionError(
                    f"students[{i}].id must match [a-z][a-z0-9_-]*"
                )
            if student_id in seen_student_ids:
                raise SubmissionError(f"duplicate student id: {student_id!r}")
            seen_student_ids.add(student_id)
            overrides = student.get("prompt_overrides") or {}
            if not isinstance(overrides, dict):
                raise SubmissionError(
                    f"students[{i}].prompt_overrides must be a mapping"
                )
            parsed_students.append({
                "id": student_id,
                "handle": student.get("handle"),
                "focus": str(student.get("focus") or ""),
                "prompt_overrides": dict(overrides),
            })
        students = tuple(parsed_students)

    default_student_id = str(raw.get("default_student_id") or students[0]["id"])
    if default_student_id not in {s["id"] for s in students}:
        raise SubmissionError(
            f"default_student_id {default_student_id!r} is not present in students"
        )

    # --- lab_id: prefer lab.yaml, fall back to hypothesis slug ---
    lab_id = raw.get("lab_id") or fm.get("slug")
    if not lab_id:
        raise SubmissionError(
            "lab_id missing; provide it in lab.yaml or hypothesis.md slug"
        )
    if not isinstance(lab_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", lab_id
    ):
        raise SubmissionError(
            "lab_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}"
        )

    allowed_patterns = tuple(src_block.get("allowed_patterns") or ("**/*.py",))
    for i, pattern in enumerate(allowed_patterns):
        if (
            not isinstance(pattern, str)
            or not pattern
            or Path(pattern).is_absolute()
            or ".." in Path(pattern).parts
        ):
            raise SubmissionError(
                f"source.allowed_patterns[{i}] must be a relative, non-traversing glob"
            )
    env_passthrough = tuple(exe.get("env_passthrough") or ())
    for i, name in enumerate(env_passthrough):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise SubmissionError(
                f"executor.env_passthrough[{i}] is not a valid environment variable name"
            )
        from efferents.agents.model_client import PROVIDER_KEY_ENV
        daemon_credentials = set(PROVIDER_KEY_ENV.values()) | {"NTFY_TOPIC"}
        if name in daemon_credentials:
            raise SubmissionError(
                f"executor.env_passthrough[{i}] must not name daemon credentials ({name})"
            )

    run_timeout_s = int(exe.get("run_timeout_s", 7200))
    smoke_timeout_s = int(exe.get("smoke_timeout_s", 300))
    daily_cap_usd = float(budget_raw.get("daily_cap_usd", 10.0))
    flat_digest_epsilon = float(metrics_raw.get("flat_digest_epsilon", 0.005))
    max_open_campaigns = int(raw.get("max_open_campaigns_per_student", 2))
    gain_threshold = float(peer_review_raw.get("gain_threshold", 0.05))
    accept_mean = float(peer_review_raw.get("accept_mean_threshold", 6.0))
    accept_min = int(peer_review_raw.get("accept_min_threshold", 4))
    if run_timeout_s <= 0 or smoke_timeout_s <= 0:
        raise SubmissionError("executor timeouts must be positive")
    if daily_cap_usd < 0:
        raise SubmissionError("budget.daily_cap_usd must be non-negative")
    if flat_digest_epsilon < 0:
        raise SubmissionError("metrics.flat_digest_epsilon must be non-negative")
    if max_open_campaigns <= 0:
        raise SubmissionError("max_open_campaigns_per_student must be positive")
    if gain_threshold < 0:
        raise SubmissionError("peer_review.gain_threshold must be non-negative")
    if not 0 <= accept_mean <= 10 or not 0 <= accept_min <= 10:
        raise SubmissionError("peer-review acceptance thresholds must be between 0 and 10")

    prompts_dir_candidate = submission_dir / "prompts"
    prompts_dir = prompts_dir_candidate if prompts_dir_candidate.is_dir() else None

    return LabConfig(
        lab_id=lab_id,
        domain=raw.get("domain", "unspecified"),
        subdomain=raw.get("subdomain"),
        pi_handle=raw.get("pi_handle"),
        code_repo=raw.get("code_repo"),
        source=Source(
            dir=src_dir,
            allowed_patterns=allowed_patterns,
        ),
        executor=Executor(
            run_command=run_command,
            smoke_command=exe.get("smoke_command"),
            config_template=abs_config_template,
            run_timeout_s=run_timeout_s,
            smoke_timeout_s=smoke_timeout_s,
            env_passthrough=env_passthrough,
        ),
        metrics=Metrics(
            headline=Headline(column=headline_col, direction=headline_dir),
            panels=panels,
            flat_digest_epsilon=flat_digest_epsilon,
            bucket_axes=bucket_axes,
        ),
        budget=Budget(
            daily_cap_usd=daily_cap_usd,
            sonnet_default=bool(budget_raw.get("sonnet_default", True)),
        ),
        autonomy=Autonomy(
            coder_enabled=bool(autonomy_raw.get("coder_enabled", False)),
        ),
        default_student_id=default_student_id,
        max_open_campaigns_per_student=max_open_campaigns,
        students=students,
        peer_review_enabled=bool(peer_review_raw.get("enabled", False)),
        peer_review_gain_threshold=gain_threshold,
        peer_review_accept_mean_threshold=accept_mean,
        peer_review_accept_min_threshold=accept_min,
        prompts_dir=prompts_dir,
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
    subdomain: str | None = None
    code_repo: str | None = None
    autonomy: Autonomy = field(default_factory=Autonomy)
    default_student_id: str = "primary"
    max_open_campaigns_per_student: int = 2
    students: tuple[dict, ...] = field(default_factory=lambda: (
        {"id": "primary", "handle": None, "focus": "", "prompt_overrides": {}},
    ))
    peer_review_enabled: bool = False
    peer_review_gain_threshold: float = 0.05
    peer_review_accept_mean_threshold: float = 6.0
    peer_review_accept_min_threshold: int = 4
    prompts_dir: Path | None = None

    @classmethod
    def from_submission(
        cls, submission_dir: Path | str, check_paths: bool = True
    ) -> "LabConfig":
        """Load a LabConfig from a submission directory.

        The directory must contain:
          - hypothesis.md  (with YAML frontmatter; falsifiability_gate must be 'passed')
          - lab.yaml       (executor, source, metrics configuration)

        Pass ``check_paths=False`` to skip source.dir / config_template existence
        checks.  Useful when loading config for read-only purposes (e.g. the
        dashboard serve command invoked against an already-initialised lab/ dir
        whose source tree is rooted in the parent submission directory).
        """
        submission_dir = Path(submission_dir).resolve()
        fm = _parse_hypothesis(submission_dir / "hypothesis.md")
        raw = _load_lab_yaml(submission_dir / "lab.yaml")
        return _build_labconfig(fm, raw, submission_dir, check_paths=check_paths)


# ---------------------------------------------------------------------------
# Active-config accessors and legacy-constant shim helper.
# ---------------------------------------------------------------------------
_active: LabConfig | None = None


def set_config(cfg: LabConfig) -> None:
    """Install the active LabConfig and synchronize legacy module attributes.

    Several Phase-A modules still read ``lab.LAB_ID`` and related attributes.
    Synchronizing them here keeps those paths correct while the remaining
    callers migrate to ``get_config()``.
    """
    global _active, LAB_ID, DOMAIN, SUBDOMAIN, PI_HANDLE, CODE_REPO
    global DEFAULT_STUDENT_ID, MAX_OPEN_CAMPAIGNS_PER_STUDENT, STUDENTS
    global PEER_REVIEW_ENABLED, PEER_REVIEW_GAIN_THRESHOLD
    global PEER_REVIEW_ACCEPT_MEAN_THRESHOLD
    global PEER_REVIEW_ACCEPT_MIN_THRESHOLD
    _active = cfg
    LAB_ID = cfg.lab_id
    DOMAIN = cfg.domain
    SUBDOMAIN = cfg.subdomain
    PI_HANDLE = cfg.pi_handle
    CODE_REPO = cfg.code_repo or ""
    DEFAULT_STUDENT_ID = cfg.default_student_id
    MAX_OPEN_CAMPAIGNS_PER_STUDENT = cfg.max_open_campaigns_per_student
    STUDENTS = [dict(student) for student in cfg.students]
    PEER_REVIEW_ENABLED = cfg.peer_review_enabled
    PEER_REVIEW_GAIN_THRESHOLD = cfg.peer_review_gain_threshold
    PEER_REVIEW_ACCEPT_MEAN_THRESHOLD = cfg.peer_review_accept_mean_threshold
    PEER_REVIEW_ACCEPT_MIN_THRESHOLD = cfg.peer_review_accept_min_threshold


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
        "SUBDOMAIN": cfg.subdomain,
        "PI_HANDLE": cfg.pi_handle,
        "CODE_REPO": cfg.code_repo or "",
        "DEFAULT_STUDENT_ID": cfg.default_student_id,
        "MAX_OPEN_CAMPAIGNS_PER_STUDENT": cfg.max_open_campaigns_per_student,
        "STUDENTS": list(cfg.students),
        "PEER_REVIEW_ENABLED": cfg.peer_review_enabled,
        "PEER_REVIEW_GAIN_THRESHOLD": cfg.peer_review_gain_threshold,
        "PEER_REVIEW_ACCEPT_MEAN_THRESHOLD": cfg.peer_review_accept_mean_threshold,
        "PEER_REVIEW_ACCEPT_MIN_THRESHOLD": cfg.peer_review_accept_min_threshold,
    }
    if name not in mapping:
        raise AttributeError(name)
    return mapping[name]
