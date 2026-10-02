# packaging/windows — TANUQ FREE Windows installer (prototype)

Builds a **per-user Windows installer** for TANUQ FREE using the
architecture approved by the Owner:

- **Embedded CPython 3.12 (win64)** + **pre-installed TANUQ** (PyPI
  `event-sourced-ai-runtime==<version>`) — *no Python, no Git, no pip
  needed on the target machine*; works offline after install.
- **Inno Setup** installer, `PrivilegesRequired=lowest` → per-user to
  `%LOCALAPPDATA%\Programs\TANUQ` (no admin).
- Launchers: `tanuq.cmd` (CLI passthrough, `python -m tanuq`) and
  `TANUQ-UI.cmd` (starts the local UI server in a minimized window and
  opens `http://127.0.0.1:8770`).
- **Why not PyInstaller:** the product spawns real subprocesses through
  `sys.executable` (verification runs `-m pytest`, UI adapter runs
  `-m tanuq.claude_code_adapter`). In a frozen executable
  `sys.executable` points at the frozen exe itself, breaking that model
  without core-code changes. A real embedded `python.exe` keeps the
  existing governance/verification code untouched.

## Files

| File | Purpose |
|---|---|
| `build_installer.ps1` | Acquires Inno Setup (if missing) + embeddable CPython, installs TANUQ into the embedded env, collects license attributions, verifies version (`0.6.0`), compiles the installer, writes SHA-256. |
| `tanuq.iss` | Inno Setup script (per-user, Start Menu + Desktop shortcut, clean uninstall). |
| `tanuq.cmd` | CLI launcher shim (payload). |
| `TANUQ-UI.cmd` | UI launcher shim (starts server, opens browser; token via `tanuq token` if asked — same as QUICKSTART). |
| `test_installer.ps1` | Silent install → PATH-sanitized E2E (version/help/init/propose/approve/execute/verify/ui) → uninstall. |
| `.gitignore` | Ignores `work/` and `out/` (build scratch/artifacts). |

## Build

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_installer.ps1
```

Outputs (git-ignored):

- `packaging/windows/out/TANUQ-Setup-0.6.0.exe`
- `packaging/windows/out/SHA256SUMS.txt`

Network is required **at build time** (Inno/embed downloads, PyPI wheel).
**Install time is offline.**

## Test

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\test_installer.ps1
```

Covers: silent per-user install, payload E2E with **PATH reduced to
`System32`** (proves no system Python/Git dependency), isolated
`HOME`/`USERPROFILE` (no pollution of the real `~/.tanuq`), full
governed chain (`init → propose → approve → execute → VERIFIED →
verify → history`), UI port check, silent uninstall + shortcut cleanup.

## Limitations (honest)

- Tested on the developer machine, **not** on a clean Windows VM without
  Python/Git; no offline (network-cut) install test yet.
- The admin/non-admin split was not drop-privilege tested (the installer
  itself requests no elevation: `PrivilegesRequired=lowest`).
- **No code signing yet** (Owner decision) → SmartScreen/Defender
  warnings are expected until a certificate is used.
- No auto-update; Windows 10/11 x64 only (no ARM64).
- First UI visit may ask for the token (`tanuq token`) — documented
  QUICKSTART behaviour, not removed by this installer.

## Version sync

Installer, payload and PyPI wheel are pinned to the same version
(default `0.6.0`). `build_installer.ps1` fails the build if
`importlib.metadata.version("event-sourced-ai-runtime")` or
`tanuq --version` inside the payload do not report that version.

## License attribution

`licenses/` inside the installed payload contains:

- `python-PSF-LICENSE.txt` — embedded CPython license
- `<dist-info>/licenses/…` — license files shipped by each dependency
  (requests, certifi, pytest, …)
- `THIRD_PARTY_LICENSES.txt` — index of the above
