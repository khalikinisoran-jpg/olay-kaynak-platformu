# Tanuq — Quickstart

```bash
# 1. Install (from the repository)
pip install -e .

# 2. Protect a workspace (interactive; add --yes for defaults)
cd path/to/your/project
tanuq init

# 3. Check protection
tanuq status

# 4. Submit a change (agent hook mode)
echo '{"path": "notes.txt", "old_content": "", "new_content": "hi", "reason": "demo"}' \
  | tanuq propose --stdin-json

# 4b. Creating a NEW file is HIGH risk - human approval is required first:
tanuq approve

# 5. Apply it
tanuq execute

# 6. Look at what happened
tanuq history
tanuq verify
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
