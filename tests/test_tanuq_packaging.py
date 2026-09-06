"""Release-candidate packaging regression test.

Proves the wheel is self-contained: a fresh venv OUTSIDE the repository,
with the wheel installed and no PYTHONPATH, running from a working
directory outside the repo, must serve the UI from the INSTALLED
package's static assets and pass the full product smoke.

This test builds a wheel and creates a venv, so it is slow; it exists
to protect the packaging contract, not the security core.
"""
import json
import os
import subprocess
import sys
import urllib.request
import venv
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REPO_MARKER = "event-sourcing-platform"


def _run(cmd, cwd, timeout=300):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    home = Path(cwd) / "home"
    home.mkdir(exist_ok=True)
    env["USERPROFILE"] = str(home)
    env["HOME"] = str(home)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def release_env(tmp_path_factory):
    base = tmp_path_factory.mktemp("tanuq_rc")
    wheels = base / "wheels"
    wheels.mkdir()

    build = _run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(wheels), str(REPO)],
        cwd=base,
    )
    assert build.returncode == 0, build.stderr
    wheel = next(wheels.glob("*.whl"))

    venv_dir = base / "venv"
    venv.create(str(venv_dir), with_pip=True)
    venv_python = venv_dir / ("Scripts" if os.name == "nt" else "bin") / "python.exe"
    if not venv_python.exists():
        venv_python = venv_dir / "bin" / "python"
    install = _run(
        [str(venv_python), "-m", "pip", "install", "--quiet", str(wheel)],
        cwd=base,
        timeout=600,
    )
    assert install.returncode == 0, install.stderr
    scripts = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    tanuq_exe = scripts / ("tanuq.exe" if os.name == "nt" else "tanuq")
    return {
        "base": base,
        "venv_python": str(venv_python),
        "tanuq": str(tanuq_exe),
        "workspace": base / "ws",
    }


def test_release_candidate_wheel_is_self_contained(release_env):
    ws = release_env["workspace"]
    ws.mkdir(exist_ok=True)
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    workdir = release_env["base"] / "outside_cwd"
    workdir.mkdir(exist_ok=True)
    tanuq = release_env["tanuq"]

    assert not str(ws).startswith(str(REPO))
    assert REPO_MARKER not in str(ws)

    help_res = _run([tanuq, "--help"], cwd=workdir)
    assert help_res.returncode == 0, help_res.stderr
    version_res = _run([tanuq, "--version"], cwd=workdir)
    assert version_res.returncode == 0
    assert "Tanuq" in version_res.stdout

    probe = _run(
        [release_env["venv_python"], "-c",
         "import tanuq, tanuq.web as web, importlib.resources as r;"
         "print(tanuq.__file__);"
         "print((r.files('tanuq') / 'static' / 'index.html').is_file());"
         "print(web.static_bytes('index.html')[:6].decode())"],
        cwd=workdir,
    )
    assert probe.returncode == 0, probe.stderr
    lines = probe.stdout.strip().splitlines()
    installed_tanuq_file = lines[0]
    assert REPO_MARKER not in installed_tanuq_file
    assert lines[1] == "True"
    assert lines[2] == "<!DOCT"

    init_res = _run([tanuq, "init", "--workspace", str(ws), "--yes"], cwd=workdir)
    assert init_res.returncode == 0, init_res.stderr
    status_res = _run([tanuq, "status", "--workspace", str(ws)], cwd=workdir)
    assert status_res.returncode == 0
    assert "Governed mode:      ON" in status_res.stdout
    assert "anchor ACTIVE" in status_res.stdout

    proposal = json.dumps({
        "path": str(ws / "demo.txt"),
        "old_content": "hello",
        "new_content": "hello installed",
        "reason": "rc smoke",
    })
    propose_env = dict(os.environ)
    propose_env.pop("PYTHONPATH", None)
    propose_env["USERPROFILE"] = str(workdir / "home")
    propose_env["HOME"] = str(workdir / "home")
    propose_input = subprocess.run(
        [tanuq, "propose", "--workspace", str(ws), "--stdin-json", "--json"],
        input=proposal, cwd=str(workdir), capture_output=True, text=True,
        timeout=120, env=propose_env,
    )
    assert propose_input.returncode == 0, propose_input.stderr
    response = json.loads(propose_input.stdout[propose_input.stdout.index("{"):])
    assert response["proposals"][0]["state"] == "PROPOSED"
    fingerprint = response["proposals"][0]["fingerprint"]
    assert len(fingerprint) == 64

    exec_res = _run([tanuq, "execute", "--workspace", str(ws)], cwd=workdir)
    assert exec_res.returncode == 0, exec_res.stdout + exec_res.stderr
    assert "terminal state: VERIFIED" in exec_res.stdout
    assert (ws / "demo.txt").read_text(encoding="utf-8") == "hello installed"

    verify_res = _run([tanuq, "verify", "--workspace", str(ws)], cwd=workdir)
    assert verify_res.returncode == 0
    assert "OVERALL: evidence is tamper-evident and intact." in verify_res.stdout

    server_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    server_env["USERPROFILE"] = str(workdir / "home")
    server_env["HOME"] = str(workdir / "home")
    server = subprocess.Popen(
        [tanuq, "ui", "--workspace", str(ws), "--port", "8817"],
        cwd=str(workdir),
        env=server_env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        import time
        served = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:8817/", timeout=2
                ) as resp:
                    served = (resp.status, resp.read().decode("utf-8"))
                break
            except Exception:
                time.sleep(0.5)
        assert served is not None, "UI did not serve /"
        assert served[0] == 200
        assert "Tanuq" in served[1]
        with urllib.request.urlopen(
            "http://127.0.0.1:8817/api/health", timeout=5
        ) as resp:
            health = json.loads(resp.read().decode("utf-8"))
        assert health["governed"] is True
        assert health["anchor"] == "ACTIVE"
    finally:
        server.terminate()
        server.wait(timeout=10)
