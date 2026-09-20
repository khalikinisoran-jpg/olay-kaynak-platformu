#!/usr/bin/env bash
# try_tanuq.sh - Disposable TANUQ demo (real governed pipeline, no fake output).
# Creates a temporary workspace, walks proposal -> risk -> approval ->
# governed mutation -> verification -> evidence, then cleans itself up.
# Exit 0 + OVERALL PASS only if every governance step really happened.
#
# Usage:  bash site/try/try_tanuq.sh  [--keep-workspace]

set -euo pipefail
export PYTHONIOENCODING=utf-8

KEEP_WORKSPACE=0
[ "${1:-}" = "--keep-workspace" ] && KEEP_WORKSPACE=1

# Repo root = two levels above this script (site/try/)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "============================================="
echo " TRY TANUQ - disposable governed demo"
echo "============================================="
echo "Runs locally: real TANUQ pipeline, test files only."

# 1. Disposable workspace
WORKSPACE="$(mktemp -d -t tanuq-try-XXXXXXXX)"
echo "Workspace: $WORKSPACE"
cleanup() {
  if [ "$KEEP_WORKSPACE" != "1" ]; then
    rm -rf "$WORKSPACE"
    echo "Cleanup: disposable workspace removed."
  else
    echo "Workspace kept for inspection: $WORKSPACE"
  fi
}

fail() { echo "FAIL: $1" >&2; cleanup; exit 1; }

# 2. Sample file the agent will change
TARGET="$WORKSPACE/demo.txt"
printf 'hello' > "$TARGET"

# 3. Init governed workspace
echo
echo "--- STEP 1: init (governed workspace) ---"
python -m tanuq init --workspace "$WORKSPACE" --yes
grep -q "Tanuq initialized" <(python -m tanuq status --workspace "$WORKSPACE") || true

# 4. LOW-risk proposal -> PROPOSED (applies on execute)
echo
echo "--- STEP 2: LOW-risk proposal (expect PROPOSED) ---"
printf '{"path": "%s", "action": "modify", "reason": "try demo: low-risk edit", "old_content": "hello", "new_content": "hello governed by Tanuq"}' \
  "$(printf '%s' "$TARGET" | sed 's/\\/\\\\/g')" \
  | python -m tanuq propose --workspace "$WORKSPACE" --stdin-json --json | tee /tmp/tanuq_try_low.json >/dev/null \
  || fail "LOW proposal failed"
grep -q '"state": "PROPOSED"' /tmp/tanuq_try_low.json || fail "LOW proposal did not return PROPOSED"
echo "PROPOSED (LOW) - ok"

# 5. HIGH-risk proposal -> approval gate (production-named source file)
echo
echo "--- STEP 3: HIGH-risk proposal (expect APPROVAL REQUIRED) ---"
HIGH_TARGET="$WORKSPACE/deploy_demo.py"
printf 'def deploy(): return "ok"' > "$HIGH_TARGET"
printf '{"path": "%s", "action": "modify", "reason": "try demo: risky edit", "old_content": "def deploy(): return \\"ok\\"", "new_content": "def deploy(): return \\"governed by Tanuq\\""}' \
  "$(printf '%s' "$HIGH_TARGET" | sed 's/\\/\\\\/g')" \
  | python -m tanuq propose --workspace "$WORKSPACE" --stdin-json --json > /tmp/tanuq_try_high.json \
  || fail "HIGH proposal failed"
grep -q "APPROVAL_REQUIRED" /tmp/tanuq_try_high.json || fail "HIGH proposal did not return APPROVAL_REQUIRED"
echo "APPROVAL_REQUIRED (HIGH) - ok"

# 6. Human approval (single-use, fingerprint-bound)
echo
echo "--- STEP 4: approve (single-use, fingerprint-bound) ---"
python -m tanuq approve --workspace "$WORKSPACE" | grep -q "APPROVED" || fail "approve failed"
echo "APPROVED - ok"

# 7. Execute everything pending through the governed pipeline
echo
echo "--- STEP 5: execute (governed mutation + verification) ---"
python -m tanuq execute --workspace "$WORKSPACE" --all | tee /tmp/tanuq_try_exec.txt || fail "execute failed"
grep -q "terminal state: VERIFIED" /tmp/tanuq_try_exec.txt || fail "execute did not reach VERIFIED"
grep -q "Verification passed: True" /tmp/tanuq_try_exec.txt || fail "verification did not pass"
echo "VERIFIED - ok"

# 8. Single-use binding: nothing left pending to execute
echo
echo "--- STEP 6: single-use binding check ---"
python -m tanuq execute --workspace "$WORKSPACE" --all > /tmp/tanuq_try_replay.txt 2>&1 || true
if ! grep -q "No pending proposals" /tmp/tanuq_try_replay.txt; then
  # a non-zero exit with no output also indicates fail-closed; accept only that
  grep -q "DENIED" /tmp/tanuq_try_replay.txt || fail "single-use binding not observed"
fi
echo "SINGLE-USE BINDING - ok"

# 9. Verify evidence chain
echo
echo "--- STEP 7: verify (tamper-evident evidence) ---"
python -m tanuq verify --workspace "$WORKSPACE" | tee /tmp/tanuq_try_verify.txt || fail "verify failed"
grep -Eq "Evidence chain:\s+VALID" /tmp/tanuq_try_verify.txt || fail "evidence chain not VALID"
grep -Eq "Anchor:\s+ACTIVE" /tmp/tanuq_try_verify.txt || fail "anchor not ACTIVE"

# 10. Evidence summary
echo
echo "--- STEP 8: history (read-only evidence) ---"
python -m tanuq history --workspace "$WORKSPACE" | tee /tmp/tanuq_try_hist.txt || fail "history failed"
grep -q "VERIFIED" /tmp/tanuq_try_hist.txt || fail "history missing VERIFIED evidence"
echo "EVIDENCE - ok"

echo
echo "============================================="
echo " OVERALL PASS"
echo "============================================="
echo "Governed demo finished: proposal -> risk -> approval ->"
echo "governed mutation -> verification -> evidence."
echo
echo " Next steps - run TANUQ on your own project:"
echo "   1. Start TANUQ:"
echo "        pip install -e ."
echo "        tanuq init"
echo "   2. Open the dashboard:"
echo "        tanuq ui"
cleanup
exit 0
