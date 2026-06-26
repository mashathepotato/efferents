"""Enable ``python -m efferents …`` as an alias for the ``efferents`` console
script. Delegates to the same argument parser used by the installed entry point.
"""
from __future__ import annotations

import sys

from efferents.cli import main

if __name__ == "__main__":
    sys.exit(main())
