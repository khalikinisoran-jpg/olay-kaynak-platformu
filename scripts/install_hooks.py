#!/usr/bin/env python3
"""Install the repository-local pre-commit secret guard (RELEASE-03).

Copies ``githooks/pre-commit`` into ``.git/hooks/pre-commit`` for the
current repository. Idempotent. Does not modify commit content.

Usage:
    python scripts/install_hooks.py
"""

import shutil
import sys
from pathlib import Path


def main() -> int:

    root = Path(__file__).resolve().parents[1]

    source = root / "githooks" / "pre-commit"
    target = root / ".git" / "hooks" / "pre-commit"

    if not source.exists():

        print(f"error: source hook missing: {source}")
        return 1

    if not target.parent.exists():

        print("error: not a git repository (missing .git/hooks).")
        return 1

    shutil.copyfile(source, target)

    try:

        target.chmod(0o755)

    except OSError:

        pass  # Windows does not enforce the exec bit via chmod

    print(f"installed pre-commit hook -> {target}")
    return 0


if __name__ == "__main__":

    sys.exit(main())
