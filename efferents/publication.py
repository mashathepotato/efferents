"""Conservative preflight checks for making a git repository public.

The checker deliberately separates machine-detectable blockers from questions
that require a human decision.  It can catch common disclosure failures, but it
cannot determine ownership, consent, export-control classification, or legal
compliance in every jurisdiction.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Literal


Severity = Literal["block", "review"]

LICENSE_FILENAMES = {
    "license",
    "license.md",
    "license.txt",
    "licence",
    "licence.md",
    "licence.txt",
    "copying",
    "copying.md",
    "copying.txt",
}

MANUAL_REVIEW_ATTESTATIONS: tuple[str, ...] = (
    "You own, or have permission to publish, the code, text, data, media, and "
    "other material, and have satisfied attribution and third-party licence terms.",
    "Any personal, confidential, human-subject, or customer data has a lawful "
    "publication basis and is limited or anonymised as required.",
    "The release does not breach contracts, NDAs, publication embargoes, patent "
    "strategy, court orders, or other confidentiality obligations.",
    "Any applicable export-control, sanctions, controlled-technology, or sector-"
    "specific approvals have been obtained.",
    "A security review has been completed; exposed credentials found in current "
    "files or git history have been revoked, not merely deleted.",
)

_SENSITIVE_EXACT_NAMES = {
    ".env",
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "kubeconfig",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
}
_SAFE_ENV_SUFFIXES = (".example", ".sample", ".template", ".defaults")
_PRIVATE_KEY_SUFFIXES = {".key", ".p12", ".pfx", ".jks", ".kdb", ".keystore"}
_REVIEW_DATA_SUFFIXES = {
    ".arrow", ".csv", ".db", ".feather", ".har", ".jsonl", ".log",
    ".ndjson", ".parquet", ".pcap", ".sav", ".sql", ".sqlite", ".tsv",
}
_REVIEW_MODEL_SUFFIXES = {
    ".ckpt", ".h5", ".joblib", ".npy", ".npz", ".onnx", ".pickle",
    ".pkl", ".pt", ".pth", ".safetensors",
}
_REVIEW_MEDIA_SUFFIXES = {
    ".avi", ".doc", ".docx", ".gif", ".jpeg", ".jpg", ".m4a", ".mov",
    ".mp3", ".mp4", ".pdf", ".png", ".ppt", ".pptx", ".svg", ".tif",
    ".tiff", ".wav", ".webm", ".xls", ".xlsx",
}
_REVIEW_ARCHIVE_SUFFIXES = {
    ".7z", ".bz2", ".gz", ".rar", ".tar", ".tgz", ".xz", ".zip",
}
_THIRD_PARTY_DIRS = {"external", "third_party", "third-party", "vendor", "vendored"}

_SECRET_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("SECRET_PRIVATE_KEY", "private-key material", re.compile(
        r"-----BEGIN (?:ENCRYPTED |OPENSSH |RSA |DSA |EC |PGP )?PRIVATE KEY-----"
    )),
    ("SECRET_AWS_ACCESS_KEY", "AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("SECRET_GITHUB_TOKEN", "GitHub token", re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{36,255}|github_pat_[A-Za-z0-9_]{40,255})\b"
    )),
    ("SECRET_ANTHROPIC_KEY", "Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("SECRET_OPENAI_KEY", "OpenAI API key", re.compile(
        r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    )),
    ("SECRET_GOOGLE_KEY", "Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("SECRET_SLACK_TOKEN", "Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("SECRET_STRIPE_KEY", "Stripe live secret key", re.compile(r"\bsk_live_[0-9A-Za-z]{16,}\b")),
    ("SECRET_AUTH_URL", "credential embedded in a URL", re.compile(
        r"[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]{4,}@", re.IGNORECASE
    )),
)
_ASSIGNED_SECRET_RE = re.compile(
    r"\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)\b"
    r"\s*[:=]\s*[\"']([^\r\n\"']{8,4096})[\"']",
    re.IGNORECASE,
)
_US_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")

_MAX_TEXT_FILE_BYTES = 10 * 1024 * 1024
_REVIEW_FILE_BYTES = 10 * 1024 * 1024
_BLOCK_FILE_BYTES = 50 * 1024 * 1024
_MAX_HISTORY_BYTES = 100 * 1024 * 1024
_MAX_FINDINGS = 250


@dataclass(frozen=True)
class PublicationFinding:
    code: str
    severity: Severity
    message: str
    path: str | None = None
    line: int | None = None
    commit: str | None = None


@dataclass
class PublicationReport:
    repository: str
    generated_at: str
    commit: str | None
    scanned_files: int
    scanned_history_bytes: int
    history_scanned: bool
    manual_review_acknowledged: bool
    reviewer: str | None
    findings: list[PublicationFinding] = field(default_factory=list)
    manual_review_attestations: tuple[str, ...] = MANUAL_REVIEW_ATTESTATIONS

    @property
    def blockers(self) -> list[PublicationFinding]:
        return [finding for finding in self.findings if finding.severity == "block"]

    @property
    def review_items(self) -> list[PublicationFinding]:
        return [finding for finding in self.findings if finding.severity == "review"]

    @property
    def status(self) -> str:
        if self.blockers:
            return "blocked"
        if not self.manual_review_acknowledged:
            return "needs_manual_review"
        return "ready"

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status
        payload["blocker_count"] = len(self.blockers)
        payload["review_count"] = len(self.review_items)
        payload["findings"] = [asdict(finding) for finding in self.findings]
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=check,
    )


def _repo_root(path: Path) -> Path | None:
    try:
        result = _git(path, "rev-parse", "--show-toplevel")
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return Path(result.stdout.strip()).resolve()


def _tracked_entries(repo: Path) -> list[tuple[str, str]]:
    result = subprocess.run(
        ["git", "ls-files", "-s", "-z"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    entries: list[tuple[str, str]] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        header, rel = raw.split(b"\t", 1)
        mode = header.split(b" ", 1)[0].decode("ascii", errors="replace")
        entries.append((rel.decode("utf-8", errors="surrogateescape"), mode))
    return entries


def _path_finding(rel: str, *, history: bool = False, commit: str | None = None) -> PublicationFinding | None:
    normalized = rel.replace("\\", "/")
    path = PurePosixPath(normalized)
    name = path.name.lower()
    suffix = Path(name).suffix.lower()
    prefix = "HISTORY_" if history else ""

    if name.startswith(".env") and not name.endswith(_SAFE_ENV_SUFFIXES):
        return PublicationFinding(
            f"{prefix}SENSITIVE_FILE", "block",
            "environment file may contain credentials or private configuration",
            normalized, commit=commit,
        )
    if name in _SENSITIVE_EXACT_NAMES or name.endswith(".tfstate"):
        return PublicationFinding(
            f"{prefix}SENSITIVE_FILE", "block",
            "credential-bearing or private configuration file is tracked",
            normalized, commit=commit,
        )
    if suffix in _PRIVATE_KEY_SUFFIXES:
        return PublicationFinding(
            f"{prefix}PRIVATE_KEY_FILE", "block",
            "private-key or keystore file is tracked",
            normalized, commit=commit,
        )
    return None


def _entropy(value: str) -> float:
    counts = {char: value.count(char) for char in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _looks_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    markers = (
        "changeme", "dummy", "example", "fake", "insert", "placeholder",
        "redacted", "replace", "sample", "test", "your_", "your-", "xxx",
    )
    return (
        not lowered
        or lowered.startswith(("${", "{{", "<"))
        or any(marker in lowered for marker in markers)
        or set(lowered) <= {"*", "x", "-", "_"}
    )


def _luhn_valid(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _scan_text(
    text: str,
    *,
    path: str,
    commit: str | None = None,
    history: bool = False,
) -> list[PublicationFinding]:
    findings: list[PublicationFinding] = []
    prefix = "HISTORY_" if history else ""

    for code, label, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if code != "SECRET_PRIVATE_KEY" and _looks_placeholder(match.group(0)):
                continue
            findings.append(PublicationFinding(
                f"{prefix}{code}", "block", f"possible {label} detected; value omitted",
                path, _line_number(text, match.start()) if not history else None, commit,
            ))

    for match in _ASSIGNED_SECRET_RE.finditer(text):
        value = match.group(2)
        if _looks_placeholder(value):
            continue
        severity: Severity = "block" if len(value) >= 16 and _entropy(value) >= 3.5 else "review"
        findings.append(PublicationFinding(
            f"{prefix}SECRET_ASSIGNMENT", severity,
            "possible hard-coded credential detected; value omitted",
            path, _line_number(text, match.start()) if not history else None, commit,
        ))

    for match in _US_SSN_RE.finditer(text):
        findings.append(PublicationFinding(
            f"{prefix}PERSONAL_IDENTIFIER", "review",
            "possible government-issued personal identifier detected; value omitted",
            path, _line_number(text, match.start()) if not history else None, commit,
        ))
    for match in _CARD_CANDIDATE_RE.finditer(text):
        if _luhn_valid(match.group(0)):
            findings.append(PublicationFinding(
                f"{prefix}PAYMENT_CARD", "block",
                "possible payment-card number detected; value omitted",
                path, _line_number(text, match.start()) if not history else None, commit,
            ))
    return findings


def _review_artifact_finding(rel: str) -> PublicationFinding | None:
    normalized = rel.replace("\\", "/")
    path = PurePosixPath(normalized)
    suffix = Path(path.name.lower()).suffix
    parts = {part.lower() for part in path.parts[:-1]}
    if parts & _THIRD_PARTY_DIRS:
        return PublicationFinding(
            "THIRD_PARTY_MATERIAL", "review",
            "vendored or third-party material requires ownership, attribution, and licence review",
            normalized,
        )
    if suffix in _REVIEW_DATA_SUFFIXES or path.name.lower().endswith(".tar.gz"):
        return PublicationFinding(
            "DATA_ARTIFACT", "review",
            "data, database, log, or capture artifact requires privacy and redistribution review",
            normalized,
        )
    if suffix in _REVIEW_MODEL_SUFFIXES:
        return PublicationFinding(
            "MODEL_ARTIFACT", "review",
            "model/checkpoint artifact requires training-data, licence, and disclosure review",
            normalized,
        )
    if suffix in _REVIEW_MEDIA_SUFFIXES:
        return PublicationFinding(
            "MEDIA_ARTIFACT", "review",
            "document or media artifact requires copyright, attribution, and personal-data review",
            normalized,
        )
    if suffix in _REVIEW_ARCHIVE_SUFFIXES:
        return PublicationFinding(
            "ARCHIVE_ARTIFACT", "review",
            "archive contents are not transparently reviewable and require manual inspection",
            normalized,
        )
    if suffix == ".ipynb":
        return PublicationFinding(
            "NOTEBOOK_OUTPUT", "review",
            "notebook outputs and metadata may contain secrets or personal/local-path information",
            normalized,
        )
    return None


def _scan_history(repo: Path) -> tuple[list[PublicationFinding], int, bool]:
    findings: list[PublicationFinding] = []

    names = _git(repo, "log", "--all", "--name-only", "--format=commit:%H", check=False)
    if names.returncode != 0:
        findings.append(PublicationFinding(
            "HISTORY_SCAN_FAILED", "block", "git history filenames could not be scanned"
        ))
        return findings, 0, False
    commit: str | None = None
    for raw_line in names.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("commit:"):
            commit = line[7:19]
        elif line:
            finding = _path_finding(line, history=True, commit=commit)
            if finding:
                findings.append(finding)

    process = subprocess.Popen(
        [
            "git", "log", "--all", "-p", "--format=commit:%H",
            "--no-ext-diff", "--no-textconv", "--", ".",
        ],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    assert process.stdout is not None
    scanned_bytes = 0
    truncated = False
    commit = None
    current_path = "(unknown path)"
    for raw_line in process.stdout:
        scanned_bytes += len(raw_line.encode("utf-8", errors="replace"))
        if scanned_bytes > _MAX_HISTORY_BYTES:
            truncated = True
            process.terminate()
            break
        line = raw_line.rstrip("\n")
        if line.startswith("commit:"):
            commit = line[7:19]
        elif line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            findings.extend(_scan_text(
                line[1:], path=current_path, commit=commit, history=True
            ))
    process.stdout.close()
    stderr = process.stderr.read() if process.stderr is not None else ""
    returncode = process.wait()
    if truncated:
        findings.append(PublicationFinding(
            "HISTORY_SCAN_INCOMPLETE", "block",
            "git history exceeded the built-in 100 MiB scan limit; use a dedicated full-history secret scanner",
        ))
    elif returncode != 0:
        findings.append(PublicationFinding(
            "HISTORY_SCAN_FAILED", "block",
            "git history content could not be scanned" + (f": {stderr.strip()[:160]}" if stderr.strip() else ""),
        ))
    return findings, scanned_bytes, not truncated and returncode == 0


def _deduplicate(findings: Iterable[PublicationFinding]) -> list[PublicationFinding]:
    unique: list[PublicationFinding] = []
    seen: set[tuple[object, ...]] = set()
    for finding in findings:
        key = (
            finding.code, finding.severity, finding.message, finding.path,
            finding.line, finding.commit,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
        if len(unique) >= _MAX_FINDINGS:
            unique.append(PublicationFinding(
                "FINDING_LIMIT", "block",
                "finding limit reached; resolve reported issues and rerun for a complete result",
            ))
            break
    return sorted(
        unique,
        key=lambda item: (
            0 if item.severity == "block" else 1,
            item.code,
            item.path or "",
            item.line or 0,
            item.commit or "",
        ),
    )


def check_public_repository(
    repository: str | Path,
    *,
    reviewer: str | None = None,
    scan_history: bool = True,
) -> PublicationReport:
    """Return a public-release report for a git repository.

    Supplying ``reviewer`` records that a named human completed the manual
    attestations.  It never suppresses machine-detected blockers.
    """
    requested = Path(repository).expanduser().resolve()
    generated_at = datetime.now(timezone.utc).isoformat()
    reviewer = reviewer.strip() if reviewer and reviewer.strip() else None
    root = _repo_root(requested) if requested.exists() else None
    if root is None:
        return PublicationReport(
            repository=str(requested),
            generated_at=generated_at,
            commit=None,
            scanned_files=0,
            scanned_history_bytes=0,
            history_scanned=False,
            manual_review_acknowledged=reviewer is not None,
            reviewer=reviewer,
            findings=[PublicationFinding(
                "NOT_GIT_REPOSITORY", "block",
                "public-release checks require an existing git repository",
            )],
        )

    findings: list[PublicationFinding] = []
    try:
        commit_result = _git(root, "rev-parse", "HEAD", check=False)
        commit = commit_result.stdout.strip() if commit_result.returncode == 0 else ""
        commit = commit or None
        entries = _tracked_entries(root)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return PublicationReport(
            repository=str(root), generated_at=generated_at, commit=None,
            scanned_files=0, scanned_history_bytes=0, history_scanned=False,
            manual_review_acknowledged=reviewer is not None, reviewer=reviewer,
            findings=[PublicationFinding(
                "GIT_READ_FAILED", "block", "tracked repository contents could not be read"
            )],
        )

    licence_paths = sorted(
        rel for rel, _ in entries
        if "/" not in rel.replace("\\", "/") and rel.lower() in LICENSE_FILENAMES
    )
    if not licence_paths:
        findings.append(PublicationFinding(
            "LICENSE_MISSING", "block",
            "no top-level LICENSE/LICENCE/COPYING file is tracked; publication terms are undefined",
        ))
    else:
        licence_path = root / licence_paths[0]
        try:
            licence_text = licence_path.read_text(errors="replace") if licence_path.is_file() else ""
        except OSError:
            licence_text = ""
        if not licence_text.strip():
            findings.append(PublicationFinding(
                "LICENSE_EMPTY", "block", "the tracked repository licence file is empty or unreadable",
                licence_paths[0],
            ))

    if commit is None:
        findings.append(PublicationFinding(
            "NO_RELEASE_COMMIT", "block",
            "repository has no committed HEAD to identify the reviewed public release",
        ))

    status = _git(root, "status", "--porcelain", "--untracked-files=all", check=False)
    if status.returncode != 0:
        findings.append(PublicationFinding(
            "GIT_STATUS_FAILED", "block", "repository status could not be determined"
        ))
    elif status.stdout.strip():
        findings.append(PublicationFinding(
            "GIT_DIRTY", "block",
            "the working tree is not clean; commit or remove changes so the reviewed tree exactly matches the intended public release",
        ))

    for rel, mode in entries:
        sensitive = _path_finding(rel)
        if sensitive:
            findings.append(sensitive)
        artifact = _review_artifact_finding(rel)
        if artifact:
            findings.append(artifact)

        path = root / rel
        if mode == "160000":
            findings.append(PublicationFinding(
                "GIT_SUBMODULE", "review",
                "git submodule requires separate source, licence, and revision review", rel,
            ))
            continue
        if mode == "120000":
            try:
                target = path.readlink() if path.is_symlink() else Path(path.read_text(errors="replace"))
            except OSError:
                findings.append(PublicationFinding(
                    "SYMLINK_UNREADABLE", "block",
                    "tracked symlink target could not be inspected", rel,
                ))
                continue
            if target.is_absolute() or ".." in target.parts:
                findings.append(PublicationFinding(
                    "SYMLINK_ESCAPE", "block",
                    "tracked symlink points outside the repository and may expose unintended files when packaged",
                    rel,
                ))
            else:
                findings.append(PublicationFinding(
                    "SYMLINK_REVIEW", "review",
                    "tracked symlink requires packaging and target review", rel,
                ))
            continue
        if not path.is_file():
            findings.append(PublicationFinding(
                "TRACKED_FILE_MISSING", "block",
                "tracked file is unavailable in the working tree; scan is incomplete", rel,
            ))
            continue

        try:
            size = path.stat().st_size
        except OSError:
            findings.append(PublicationFinding(
                "TRACKED_FILE_UNREADABLE", "block",
                "tracked file metadata could not be inspected", rel,
            ))
            continue
        if size > _BLOCK_FILE_BYTES:
            findings.append(PublicationFinding(
                "FILE_TOO_LARGE", "block",
                "file exceeds 50 MiB; inspect it separately before publication", rel,
            ))
        elif size > _REVIEW_FILE_BYTES:
            findings.append(PublicationFinding(
                "LARGE_FILE", "review",
                "file exceeds 10 MiB and requires separate content and rights review", rel,
            ))

        try:
            data = path.read_bytes()[:_MAX_TEXT_FILE_BYTES]
        except OSError:
            findings.append(PublicationFinding(
                "TRACKED_FILE_UNREADABLE", "block",
                "tracked file contents could not be inspected", rel,
            ))
            continue
        if b"\0" in data:
            if artifact is None:
                findings.append(PublicationFinding(
                    "BINARY_ARTIFACT", "review",
                    "binary content cannot be fully inspected by the built-in text scanner", rel,
                ))
            continue
        text = data.decode("utf-8", errors="replace")
        findings.extend(_scan_text(text, path=rel))

    history_bytes = 0
    history_complete = False
    if scan_history:
        history_findings, history_bytes, history_complete = _scan_history(root)
        findings.extend(history_findings)
    else:
        findings.append(PublicationFinding(
            "HISTORY_SCAN_SKIPPED", "block",
            "reachable git history was not scanned; public release cannot be cleared",
        ))

    # The hash identifies the exact tracked path list checked without exposing
    # file contents in the report.
    tree_fingerprint = hashlib.sha256(
        "\0".join(sorted(rel for rel, _ in entries)).encode("utf-8", errors="surrogateescape")
    ).hexdigest()[:16]
    findings.append(PublicationFinding(
        "SCAN_SCOPE", "review",
        f"manual review covers {len(entries)} tracked paths (scope {tree_fingerprint}) and "
        + ("reachable git history" if history_complete else "an incomplete or skipped history scan"),
    ))

    return PublicationReport(
        repository=str(root),
        generated_at=generated_at,
        commit=commit,
        scanned_files=len(entries),
        scanned_history_bytes=history_bytes,
        history_scanned=history_complete,
        manual_review_acknowledged=reviewer is not None,
        reviewer=reviewer,
        findings=_deduplicate(findings),
    )


def format_publication_report(report: PublicationReport) -> str:
    """Human-readable, secret-redacted CLI rendering."""
    lines = [
        f"PUBLIC RELEASE CHECK: {report.status.upper()}",
        f"repository={report.repository}",
        f"commit={report.commit or 'unavailable'}",
        f"scanned_files={report.scanned_files}",
        f"history_scanned={'yes' if report.history_scanned else 'no'}",
        f"blockers={len(report.blockers)} review_items={len(report.review_items)}",
    ]
    for finding in report.findings:
        location = finding.path or "repository"
        if finding.line is not None:
            location += f":{finding.line}"
        if finding.commit:
            location += f"@{finding.commit}"
        lines.append(
            f"[{finding.severity.upper()}] {finding.code} {location}: {finding.message}"
        )
    lines.extend(["", "Manual publication attestations:"])
    for item in report.manual_review_attestations:
        lines.append(f"- {item}")
    if not report.manual_review_acknowledged:
        lines.extend([
            "",
            "After resolving blockers and completing the manual review, rerun with:",
            '  --acknowledge-manual-review "Reviewer name"',
        ])
    elif report.reviewer:
        lines.append(f"Manual review acknowledged by: {report.reviewer}")
    lines.append(
        "This preflight reduces disclosure risk; it is not legal advice or a guarantee of compliance."
    )
    return "\n".join(lines) + "\n"
