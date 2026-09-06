"""Tanuq product latency benchmark (measure-first; no optimization).

Generates a synthetic Python workspace, then measures the product
workflow latencies end-to-end against the real governed runtime:

    startup (load_environment)  -> Kernel recovery + assembly
    propose                     -> scope + governance + pending store
    execute                     -> governed pipeline + verification
                                   (compileall + pytest over workspace)
    verify                      -> full chain re-hash + anchor check
    incidents                   -> reconciliation + chain/anchor scan

Usage:
    python benchmarks/tanuq_product_benchmark.py [--files 150] [--keep]

Numbers are local-machine observations, not production benchmarks.
"""
import argparse
import json
import shutil
import statistics
import tempfile
import time
from pathlib import Path

from tanuq import agent_adapter
from tanuq.config import init_workspace
from tanuq.incidents import collect_incidents
from tanuq.runtime import load_environment

FILE_TEMPLATE = "def func_{i}(x):\n    return x + {i}\n"


def build_workspace(root: Path, file_count: int) -> Path:
    ws = root / "bench-ws"
    ws.mkdir(parents=True, exist_ok=True)
    src = ws / "src"
    src.mkdir(exist_ok=True)
    for i in range(file_count):
        (src / f"mod_{i}.py").write_text(
            FILE_TEMPLATE.format(i=i), encoding="utf-8"
        )
    init_workspace(ws)
    return ws


def measure(ws: Path, file_count: int) -> dict:
    results = {}

    t0 = time.perf_counter()
    env = load_environment(ws)
    results["startup_s"] = time.perf_counter() - t0

    target = ws / "src" / "mod_0.py"
    old = target.read_text(encoding="utf-8")
    payload = json.dumps({
        "path": str(target),
        "old_content": old,
        "new_content": old + f"# touched {file_count}\n",
        "reason": "benchmark touch",
    })

    samples = []
    for _ in range(3):
        t0 = time.perf_counter()
        agent_adapter.propose(env, payload)
        samples.append(time.perf_counter() - t0)
    results["propose_s"] = statistics.median(samples)

    t0 = time.perf_counter()
    agent_adapter.approve(env)  # no-op for LOW; included for completeness
    results["approve_noop_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    executed = agent_adapter.execute(env)
    results["execute_s"] = time.perf_counter() - t0
    results["execute_terminal"] = executed.get("terminal")

    t0 = time.perf_counter()
    from tanuq.config import read_anchor_key
    from tanuq.evidence import chain_status
    from tanuq.config import tanuq_data_dir
    chain_status(
        tanuq_data_dir(ws),
        read_anchor_key(ws).encode() if isinstance(read_anchor_key(ws), str)
        else read_anchor_key(ws),
    )
    results["verify_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    collect_incidents(env)
    results["incidents_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    from tanuq.evidence import lineage
    lineage(env)
    results["lineage_s"] = time.perf_counter() - t0

    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--files", type=int, default=150)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    root = Path(tempfile.mkdtemp(prefix="tanuq-bench-"))
    print(f"workspace: {root/'bench-ws'} ({args.files} python files)")
    try:
        ws = build_workspace(root, args.files)
        results = measure(ws, args.files)
        print(json.dumps(results, indent=2))
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
