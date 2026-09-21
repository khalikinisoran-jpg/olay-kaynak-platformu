import json, os, subprocess, sys, shutil
REPO = r"C:\Projects\event-sourcing-platform"
MASTER = os.path.join(os.environ.get("TEMP", r"C:\Users\REŞAT\AppData\Local\Temp"), "e5-master")
SNAPD = os.path.join(os.environ.get("TEMP", r"C:\Users\REŞAT\AppData\Local\Temp"),
                     "e5-run01", "e5-master-snap")

def restore():
    if os.path.exists(MASTER): shutil.rmtree(MASTER)
    shutil.copytree(SNAPD, MASTER)

def cli(args):
    co = os.path.join(MASTER, "_o.txt")
    qargs = " ".join(f'"{a}"' for a in args)
    cmd = f'"{sys.executable}" -m tanuq {qargs} > "{co}" 2> "{os.path.join(MASTER, "_e.txt")}"'
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run(cmd, shell=True, cwd=REPO, env=env)
    raw = open(co, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "utf-8", "cp1254"):
        try: return p.returncode, raw.decode(enc)
        except Exception: continue
    return p.returncode, raw.decode("utf-8", errors="replace")

# pristine restore, then effective payload tampering on the LAST event
restore()
ev = os.path.join(MASTER, ".tanuq", "data", "events.jsonl")
lines = open(ev, encoding="utf-8").read().splitlines()
last = json.loads(lines[-1])
last["payload"]["effective_tamper_marker"] = "TAMPERED-PAYLOAD"
lines[-1] = json.dumps(last, ensure_ascii=False)
open(ev, "w", encoding="utf-8", newline="").write("\n".join(lines) + "\n")
print("payload tampered on last event (hash fields untouched)")

code, out = cli(["verify", "--workspace", MASTER])
flat = " ".join(out.split())
verdict = "VALID" if ("VALID" in flat and "INVALID" not in flat and len(flat) > 20) else "INVALID/FAIL-CLOSED"
print("verify verdict:", verdict)
print("detail:", flat[:260])

# also: modify a MIDDLE event (breaks the chain link by construction)
restore()
lines = open(ev, encoding="utf-8").read().splitlines()
mid = json.loads(lines[len(lines)//2])
mid["payload"]["effective_tamper_marker"] = "TAMPERED-PAYLOAD"
lines[len(lines)//2] = json.dumps(mid, ensure_ascii=False)
open(ev, "w", encoding="utf-8", newline="").write("\n".join(lines) + "\n")
print("payload tampered on a MIDDLE event (hash fields untouched)")
code, out = cli(["verify", "--workspace", MASTER])
flat = " ".join(out.split())
verdict = "VALID" if ("VALID" in flat and "INVALID" not in flat and len(flat) > 20) else "INVALID/FAIL-CLOSED"
print("verify verdict:", verdict)
print("detail:", flat[:260])
