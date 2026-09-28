# Tanuq — Quickstart

```bash
# 1. Install (from the repository)
pip install -e .

# 2. Protect a workspace (interactive; add --yes for defaults)
cd path/to/your/project
tanuq init

# 3. Check protection
tanuq status

# 4. Submit a NEW-file proposal (agent hook mode; action=create is HIGH risk)
echo '{"path": "notes.txt", "action": "create", "old_content": "", "new_content": "hi", "reason": "demo"}' \
  | tanuq propose --stdin-json
# propose prints this proposal's Fingerprint (e.g. "Fingerprint: 1a2b3c4d5e6f")

# 4b. action=create is always HIGH risk - human approval is required first.
#     The approval is single-use and bound to the SAME fingerprint from step 4:
tanuq approve
# exact binding (optional): tanuq approve --fingerprint <fingerprint-from-step-4>

# 5. Execute the SAME pending proposal; the single-use approval is consumed here:
tanuq execute
# same binding (optional): tanuq execute --fingerprint <fingerprint-from-step-4>

# 6. Look at what happened
tanuq history
tanuq verify
```

Action choices: `create` targets a NEW file and requires `old_content`
to be exactly `""`; new-file creation is always HIGH risk, so steps
4 → 4b → 5 above run against the SAME proposal and its single
fingerprint. `modify` targets an EXISTING file and `old_content` must
match the current file content (a mismatch is warned at propose time
and DENIED as stale at execute time; a target that does not exist yet
is DENIED at validation). Explicit `modify` example, once `notes.txt`
exists with content `hi`:

```bash
echo '{"path": "notes.txt", "action": "modify", "old_content": "hi", "new_content": "hello", "reason": "demo update"}' \
  | tanuq propose --stdin-json
```

Risky changes (HIGH/CRITICAL — for example anything containing
credentials) pause at approval:

```bash
tanuq approve
tanuq execute
```

Or use the product UI instead of the CLI:

```bash
tanuq ui                 # open http://127.0.0.1:8770
# token for the UI: run 'tanuq token' and paste it in the browser once
```

If verification fails, the change is rolled back automatically and the
rollback is recorded as evidence.

See `docs/USER_GUIDE.md` for the full guide and the honest list of
what Tanuq does not do.
