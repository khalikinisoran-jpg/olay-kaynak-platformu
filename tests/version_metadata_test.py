"""Version consistency tests.

Real friction finding: `tanuq --version` reported a hard-coded 0.1.0
while the packaging metadata (pyproject.toml) is 0.6.0. The single
source of truth for the user-visible version is the installed package
metadata (importlib.metadata — stdlib, no new dependency); the
hard-coded value is only a fallback for a bare source tree.
"""
import json
import subprocess
import sys

from importlib.metadata import version as _package_version

import tanuq


def test_dunder_version_matches_packaging_metadata():
    assert tanuq.__version__ == _package_version("event-sourced-ai-runtime")


def test_cli_version_flag_matches_packaging_metadata():
    proc = subprocess.run(
        [sys.executable, "-m", "tanuq", "--version"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert f"Tanuq {tanuq.__version__}" in proc.stdout
    assert "0.1.0" not in proc.stdout


def test_evidence_module_reports_packaging_version():
    # evidence.py embeds the version in exported evidence bundles; it
    # imports it from the tanuq package and must stay consistent with
    # the packaging metadata as well.
    import tanuq.evidence as evidence_module

    assert evidence_module.__version__ == _package_version(
        "event-sourced-ai-runtime"
    )
