# E3 RUN-01 runner — real TANUQ CLI, disposable workspaces, inert synthetic steps.
import json, os, subprocess, sys, io, hashlib, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stdout.reconfigure(line_buffering=True)
REPO = r"C:\Projects\event-sourcing-platform"
TMP = os.path.join(os.environ.get("TEMP", r"C:\Users\REŞAT\AppData\Local\Temp"), "e3-run01")
if os.path.exists(TMP): shutil.rmtree(TMP)
os.makedirs(TMP)
FX = json.load(open(os.path.join(REPO, "docs", "research",
     "agent_escape_e3_fixtures_run01.json"), encoding="utf-8"))
R = {"fixtures_sha": hashlib.sha256(open(os.path.join(REPO, "docs", "research",
     "agent_escape_e3_fixtures_run01.json"), "rb").read()).hexdigest().upper(),
     "workspaces": {}}

def cli(ws, args, stdin=None):
    co, ce = os.path.join(ws, "_o.txt"), os.path.join(ws, "_e.txt")
    fin = ""
    if stdin:
        sp = os.path.join(ws, "_in.json")
        with open(sp, "w", encoding="utf-8", newline="") as f:
            f.write(stdin)
        fin = f' < "{sp}"'
    qargs = " ".join(f'"{a}"' for a in args)
    cmd = f'"{sys.executable}" -m tanuq {qargs}{fin} > "{co}" 2> "{ce}"'
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run(cmd, shell=True, cwd=REPO, env=env)
    raw = open(co, "rb").read()
    txt = None
    for enc in ("utf-8-sig", "utf-16", "utf-8", "cp1254"):
        try: txt = raw.decode(enc); break
        except Exception: continue
    return {"exit": p.returncode, "out": txt or ""}

def snap(ws, files):
    return {f: open(os.path.join(ws, f), encoding="utf-8", newline="").read()
            for f in files if os.path.exists(os.path.join(ws, f))}

for ch in FX["chains"]:
    cls = ch["class"]
    files = ch["initial_files"]
    # --- drift workspace ---
    dws = os.path.join(TMP, cls + "-drift")
    os.makedirs(os.path.join(dws, "core"), exist_ok=True)
    for f, c in files.items():
        with open(os.path.join(dws, f), "w", encoding="utf-8", newline="") as fh:
            fh.write(c)
    R["workspaces"][dws] = {"chain": cls, "kind": "drift", "steps": []}
    cli(dws, ["init", "--workspace", dws, "--yes"])
    prev_new = {f: c for f, c in files.items()}
    for st in ch["drift_steps"]:
        fpath = os.path.join(dws, st["fixture"]["path"].replace("/", os.sep))
        fx = dict(st["fixture"])
        fx["path"] = os.path.join(dws, fx["path"].replace("/", os.sep))
        pr = cli(dws, ["propose", "--workspace", dws, "--stdin-json", "--json"],
                 json.dumps(fx))
        try:
            pj = json.loads(pr["out"])["proposals"][0]
            pstate, pfp, prisk = pj["state"], pj["fingerprint"], pj["risk"]
        except Exception:
            pstate, pfp, prisk = "PARSE-FAIL", None, None
        ex = cli(dws, ["execute", "--workspace", dws, "--fingerprint", pfp]) if pfp else {"out": ""}
        term = " ".join(ex["out"].split())
        term = term[term.find("terminal state"):term.find("terminal state")+60] if "terminal state" in term else term[:80]
        cur = open(fpath, encoding="utf-8", newline="").read()
        R["workspaces"][dws]["steps"].append({
            "step": st["step"], "propose_state": pstate, "fingerprint": pfp,
            "propose_risk": prisk, "execute": term, "file_matches_new": cur == st["fixture"]["new_content"]})
        print(cls, st["step"], pstate, prisk, "|", term[:60])
    st = cli(dws, ["trajectory", "--workspace", dws])
    R["workspaces"][dws]["trajectory"] = st["out"][:1200]
    hs = cli(dws, ["history", "--workspace", dws, "--limit", "10"])
    R["workspaces"][dws]["history_tail"] = hs["out"][-900:]
    R["workspaces"][dws]["final_files"] = snap(dws, files)
    # --- control workspace ---
    cws = os.path.join(TMP, cls + "-control")
    os.makedirs(os.path.join(cws, "core"), exist_ok=True)
    for f, c in files.items():
        with open(os.path.join(cws, f), "w", encoding="utf-8", newline="") as fh:
            fh.write(c)
    R["workspaces"][cws] = {"chain": cls, "kind": "control", "steps": []}
    cli(cws, ["init", "--workspace", cws, "--yes"])
    for st in ch["control_steps"]:
        fpath = os.path.join(cws, st["fixture"]["path"].replace("/", os.sep))
        fx = dict(st["fixture"])
        fx["path"] = os.path.join(cws, fx["path"].replace("/", os.sep))
        pr = cli(cws, ["propose", "--workspace", cws, "--stdin-json", "--json"],
                 json.dumps(fx))
        try:
            pj = json.loads(pr["out"])["proposals"][0]
            pstate, pfp, prisk = pj["state"], pj["fingerprint"], pj["risk"]
        except Exception:
            pstate, pfp, prisk = "PARSE-FAIL", None, None
        ex = cli(cws, ["execute", "--workspace", cws, "--fingerprint", pfp]) if pfp else {"out": ""}
        term = " ".join(ex["out"].split())
        term = term[term.find("terminal state"):term.find("terminal state")+60] if "terminal state" in term else term[:80]
        cur = open(fpath, encoding="utf-8", newline="").read()
        R["workspaces"][cws]["steps"].append({
            "step": st["step"], "propose_state": pstate, "fingerprint": pfp,
            "propose_risk": prisk, "execute": term, "file_matches_new": cur == st["fixture"]["new_content"]})
        print(cls, st["step"], "(control)", pstate, prisk, "|", term[:60])
    st = cli(cws, ["trajectory", "--workspace", cws])
    R["workspaces"][cws]["trajectory"] = st["out"][:1200]
    R["workspaces"][cws]["final_files"] = snap(cws, files)
    # --- goal workspace (single-step baseline; propose-only, never executed) ---
    gws = os.path.join(TMP, cls + "-goal")
    os.makedirs(os.path.join(gws, "core"), exist_ok=True)
    for f, c in files.items():
        with open(os.path.join(gws, f), "w", encoding="utf-8", newline="") as fh:
            fh.write(c)
    R["workspaces"][gws] = {"chain": cls, "kind": "goal", "steps": []}
    cli(gws, ["init", "--workspace", gws, "--yes"])
    g = ch["goal"]
    gx = dict(g["direct_form"])
    gx["path"] = os.path.join(gws, gx["path"].replace("/", os.sep))
    pr = cli(gws, ["propose", "--workspace", gws, "--stdin-json", "--json"],
             json.dumps(gx))
    try:
        pj = json.loads(pr["out"])["proposals"][0]
        R["workspaces"][gws]["steps"].append({"goal": g["goal_id"],
            "propose_state": pj["state"], "fingerprint": pj["fingerprint"],
            "propose_risk": pj["risk"], "executed": False})
        print(cls, "GOAL", pj["state"], pj["risk"])
    except Exception as e:
        R["workspaces"][gws]["steps"].append({"goal": g["goal_id"], "error": repr(e), "raw": pr["out"][:300]})
        print(cls, "GOAL PARSE-FAIL", repr(pr["out"][:200]))

art = os.path.join(REPO, "docs", "research", "e3_run01_artifacts")
os.makedirs(art, exist_ok=True)
with open(os.path.join(art, "runner_results.json"), "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=1)
print("\nE3 RUN-01 execution complete; workspaces:", len(R["workspaces"]))
