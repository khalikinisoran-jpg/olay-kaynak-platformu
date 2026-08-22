import pathlib
import subprocess
import sys
import tempfile
import threading

from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.worker.patch_proposal import PatchProposal

KEY = "k" * 32

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _make_patch(path="allowed/a.py", old="old", new="new"):
    return PatchProposal(path=path, action="modify", reason="fix", old_content=old, new_content=new, allowed_paths=("allowed",))


def test_legitimate_grant_and_consume():
    tmp = tempfile.mkdtemp()
    ledger = ApprovalLedger(path=pathlib.Path(tmp) / "ledger.jsonl")
    store = ApprovalStore(ledger=ledger)
    patch = _make_patch()
    fp = patch.fingerprint()
    ap = store.grant(fp, patch.path, patch.action, "HIGH", attempt=1)
    found = store.find_valid(fp, path=patch.path, action=patch.action, risk_level="HIGH", attempt=1, patch=patch)
    assert found is not None
    assert found.approval_id == ap.approval_id


def test_sequential_duplicate_consume_denied():
    tmp = tempfile.mkdtemp()
    ledger = ApprovalLedger(path=pathlib.Path(tmp) / "ledger.jsonl")
    store = ApprovalStore(ledger=ledger)
    patch = _make_patch()
    fp = patch.fingerprint()
    store.grant(fp, patch.path, patch.action, "HIGH", attempt=1)
    patch2 = _make_patch()
    found1 = store.find_valid(fp, path=patch.path, action=patch.action, risk_level="HIGH", attempt=1, patch=patch)
    assert found1 is not None
    found2 = store.find_valid(fp, path=patch.path, action=patch.action, risk_level="HIGH", attempt=1, patch=patch2)
    assert found2 is None


def test_concurrent_threads_single_use():
    tmp = tempfile.mkdtemp()
    ledger = ApprovalLedger(path=pathlib.Path(tmp) / "ledger.jsonl")
    store = ApprovalStore(ledger=ledger)
    patch = _make_patch()
    fp = patch.fingerprint()
    store.grant(fp, patch.path, patch.action, "HIGH", attempt=1)

    results = []

    def attempt():
        p = _make_patch()
        found = store.find_valid(fp, path=p.path, action=p.action, risk_level="HIGH", attempt=1, patch=p)
        results.append(found is not None)

    threads = [threading.Thread(target=attempt) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(results) == 1


def test_concurrent_processes_single_use():
    tmp = tempfile.mkdtemp()
    helper = pathlib.Path(tmp) / "helper.py"
    helper.write_text(
        f"""
import sys
sys.path.insert(0, r"{REPO_ROOT}")
from pathlib import Path
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.worker.patch_proposal import PatchProposal
ledger_path = sys.argv[1]
fp = sys.argv[2]
path = sys.argv[3]
out = sys.argv[4]
ledger = ApprovalLedger(path=ledger_path)
store = ApprovalStore(ledger=ledger)
patch = PatchProposal(path=path, action="modify", reason="fix", old_content="old", new_content="new", allowed_paths=("allowed",))
found = store.find_valid(fp, path=path, action="modify", risk_level="HIGH", attempt=1, patch=patch)
Path(out).write_text("true" if found else "false")
""",
        encoding="utf-8",
    )
    tmp2 = tempfile.mkdtemp()
    ledger_path = pathlib.Path(tmp2) / "ledger.jsonl"
    # unanchored for speed; process lock still applies (ledger file lock)
    ledger = ApprovalLedger(path=ledger_path)
    store = ApprovalStore(ledger=ledger)
    patch = _make_patch()
    fp = patch.fingerprint()
    store.grant(fp, patch.path, patch.action, "HIGH", attempt=1)
    repeat = 10
    for _ in range(3):  # run attack multiple times with fresh ledger each iteration? Do 3 outer loops
        tmp_inner = tempfile.mkdtemp()
        lp = pathlib.Path(tmp_inner) / "ledger.jsonl"
        leg = ApprovalLedger(path=lp)
        st = ApprovalStore(ledger=leg)
        p = _make_patch()
        fpp = p.fingerprint()
        st.grant(fpp, p.path, p.action, "HIGH", attempt=1)
        outs = []
        procs = []
        for i in range(5):
            out = pathlib.Path(tmp) / f"out_{i}.txt"
            outs.append(out)
            procs.append(subprocess.Popen([sys.executable, str(helper), str(lp), fpp, p.path, str(out)]))
        for pr in procs:
            pr.wait(timeout=5)
        trues = sum(1 for o in outs if o.exists() and o.read_text().strip() == "true")
        assert trues == 1, f"expected exactly 1 success, got {trues}"


def test_concurrent_processes_anchored_single_use():
    tmp = tempfile.mkdtemp()
    helper = pathlib.Path(tmp) / "helper_a.py"
    helper.write_text(
        f"""
import sys
sys.path.insert(0, r"{REPO_ROOT}")
from pathlib import Path
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.worker.patch_proposal import PatchProposal
ledger_path = sys.argv[1]
anchor_path = sys.argv[2]
key = sys.argv[3]
fp = sys.argv[4]
path = sys.argv[5]
out = sys.argv[6]
ledger = ApprovalLedger(path=ledger_path, anchor_path=anchor_path, anchor_key=key)
store = ApprovalStore(ledger=ledger)
patch = PatchProposal(path=path, action="modify", reason="fix", old_content="old", new_content="new", allowed_paths=("allowed",))
found = store.find_valid(fp, path=path, action="modify", risk_level="HIGH", attempt=1, patch=patch)
Path(out).write_text("true:" + found.approval_id[:8] if found else "false")
""",
        encoding="utf-8",
    )
    for _ in range(3):
        tmp2 = tempfile.mkdtemp()
        lp = pathlib.Path(tmp2) / "ledger.jsonl"
        ap = pathlib.Path(tmp2) / "anchor.jsonl"
        leg = ApprovalLedger(path=lp, anchor_path=ap, anchor_key=KEY)
        st = ApprovalStore(ledger=leg)
        patch = _make_patch()
        fp = patch.fingerprint()
        st.grant(fp, patch.path, patch.action, "HIGH", attempt=1)
        outs = []
        procs = []
        for i in range(5):
            out = pathlib.Path(tmp) / f"outa_{i}.txt"
            outs.append(out)
            procs.append(subprocess.Popen([sys.executable, str(helper), str(lp), str(ap), KEY, fp, patch.path, str(out)]))
        for pr in procs:
            pr.wait(timeout=5)
        trues = sum(1 for o in outs if o.exists() and o.read_text().strip().startswith("true"))
        assert trues == 1
        # ledger should have exactly 1 consumed
        consumed = pathlib.Path(lp).read_text(encoding="utf-8").count("consumed")
        assert consumed == 1


def test_different_approvals_independently_usable():
    tmp = tempfile.mkdtemp()
    ledger = ApprovalLedger(path=pathlib.Path(tmp) / "ledger.jsonl")
    store = ApprovalStore(ledger=ledger)
    patch1 = _make_patch(path="allowed/a.py", old="old1", new="new1")
    patch2 = _make_patch(path="allowed/b.py", old="old2", new="new2")
    fp1 = patch1.fingerprint()
    fp2 = patch2.fingerprint()
    store.grant(fp1, patch1.path, patch1.action, "HIGH", attempt=1)
    store.grant(fp2, patch2.path, patch2.action, "HIGH", attempt=1)
    found1 = store.find_valid(fp1, path=patch1.path, action=patch1.action, risk_level="HIGH", attempt=1, patch=patch1)
    found2 = store.find_valid(fp2, path=patch2.path, action=patch2.action, risk_level="HIGH", attempt=1, patch=patch2)
    assert found1 is not None
    assert found2 is not None


def test_recovery_after_consumption_still_consumed():
    tmp = tempfile.mkdtemp()
    lp = pathlib.Path(tmp) / "ledger.jsonl"
    # grant + consume, then new store reload
    ledger = ApprovalLedger(path=lp)
    store = ApprovalStore(ledger=ledger)
    patch = _make_patch()
    fp = patch.fingerprint()
    store.grant(fp, patch.path, patch.action, "HIGH", attempt=1)
    found = store.find_valid(fp, path=patch.path, action=patch.action, risk_level="HIGH", attempt=1, patch=patch)
    assert found is not None
    # new process reload
    ledger2 = ApprovalLedger(path=lp)
    store2 = ApprovalStore(ledger=ledger2)
    # same fingerprint should be denied
    patch2 = _make_patch()
    found2 = store2.find_valid(fp, path=patch.path, action=patch.action, risk_level="HIGH", attempt=1, patch=patch2)
    assert found2 is None


def test_wrong_key_rejected():
    tmp = tempfile.mkdtemp()
    lp = pathlib.Path(tmp) / "ledger.jsonl"
    ap = pathlib.Path(tmp) / "anchor.jsonl"
    ledger = ApprovalLedger(path=lp, anchor_path=ap, anchor_key=KEY)
    store = ApprovalStore(ledger=ledger)
    patch = _make_patch()
    store.grant(patch.fingerprint(), patch.path, patch.action, "HIGH", attempt=1)
    # wrong key should fail closed on reload
    try:
        ApprovalLedger(path=lp, anchor_path=ap, anchor_key="x" * 32)
        assert False, "should have raised"
    except Exception:
        pass


def test_corrupted_ledger_fail_closed():
    tmp = tempfile.mkdtemp()
    lp = pathlib.Path(tmp) / "ledger.jsonl"
    ledger = ApprovalLedger(path=lp)
    store = ApprovalStore(ledger=ledger)
    patch = _make_patch()
    store.grant(patch.fingerprint(), patch.path, patch.action, "HIGH", attempt=1)
    # corrupt last line
    text = lp.read_text(encoding="utf-8")
    lp.write_text(text + "NOT_JSON\n", encoding="utf-8")
    try:
        ApprovalLedger(path=lp).load()
        assert False
    except RuntimeError:
        pass


def test_anchor_mismatch_rejected():
    tmp = tempfile.mkdtemp()
    lp = pathlib.Path(tmp) / "ledger.jsonl"
    ap = pathlib.Path(tmp) / "anchor.jsonl"
    ledger = ApprovalLedger(path=lp, anchor_path=ap, anchor_key=KEY)
    store = ApprovalStore(ledger=ledger)
    patch = _make_patch()
    store.grant(patch.fingerprint(), patch.path, patch.action, "HIGH", attempt=1)
    # truncate ledger
    lines = lp.read_text(encoding="utf-8").splitlines()
    lp.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    try:
        ApprovalLedger(path=lp, anchor_path=ap, anchor_key=KEY).load()
        assert False
    except RuntimeError:
        pass
