"""Tanuq — local agent governance runtime.

User-facing product shell over the existing governed runtime core
(`simulation/` package). Tanuq adds installation, init, config, a
product CLI and an agent adapter on top of the proven governance
chain; it never reimplements or bypasses it.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version

try:
    # Single source of truth: the packaging metadata (pyproject.toml).
    # Keeps `tanuq --version` consistent with the installed release
    # instead of drifting from a hard-coded copy.
    __version__ = _package_version("event-sourced-ai-runtime")
except PackageNotFoundError:  # running from a bare source tree
    __version__ = "0.1.0"

PRODUCT_NAME = "Tanuq"
PRODUCT_TAGLINE = "AI works. You stay in control."
