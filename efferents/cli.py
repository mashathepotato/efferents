"""efferents CLI entry point.

  efferents validate --submission <dir>
  efferents start    --submission <dir> [--detach] [--lab-root <path>]
  efferents status   [--lab-id <id>]
  efferents stop     --lab-id <id>
  efferents list

The `main(argv=None)` entry point is exposed for tests; pyproject.toml
console_scripts will point at `efferents.cli:main` (Task 16).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from efferents.lab import LabConfig, SubmissionError


def _cmd_validate(args: argparse.Namespace) -> int:
    sub = Path(args.submission).resolve()
    try:
        cfg = LabConfig.from_submission(sub)
    except SubmissionError as e:
        print(f"validation failed: {e}", file=sys.stderr)
        return 1
    print(f"OK lab_id={cfg.lab_id} domain={cfg.domain} source_dir={cfg.source.dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="efferents")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate", help="Validate a submission directory")
    p_validate.add_argument("--submission", required=True)
    p_validate.set_defaults(func=_cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
