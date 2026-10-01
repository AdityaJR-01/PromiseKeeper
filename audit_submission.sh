#!/bin/bash
# Pre-submission audit. Everything here runs on the local memory backend: no network.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=src
export PK_MEMORY_BACKEND=local
export PK_STORE_DIR=.pk_store_audit
trap 'rm -rf .pk_store_audit' EXIT       # clean up even when a step fails

echo "--- Running Pre-Submission Audit ---"

# Whole repo, not just README/docs: the word must not appear anywhere tracked or untracked
# (git history is not scanned -- check commit messages by hand).
if grep -rniE 'hack-?a-?thon' . --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.pytest_cache --exclude-dir=.pk_store_audit; then
    echo "FAIL: Prohibited event word found. Clean the files listed above."
    exit 1
fi

if git ls-files | grep -E '(^|/)\.env$'; then
    echo "FAIL: .env file is tracked by Git. Untrack it."
    exit 1
fi

if git ls-files | grep -E '(^|/)\.pk_store'; then
    echo "FAIL: local memory store is tracked by Git."
    exit 1
fi

echo "--- Running test suite (local backend, no network required) ---"
pytest -q

echo "--- Cold-start demo must be honest (no evidence -> insufficient_evidence) ---"
rm -rf .pk_store_audit
python -m promisekeeper.cli demo --json | python -c '
import json, sys
d = json.load(sys.stdin)
assert d["decision"] == "insufficient_evidence" and d["memories_used"] == 0, d
print("ok:", d["decision"])'

echo "--- Seeded demo must exercise the real pipeline end to end ---"
python -m promisekeeper.cli seed
python -m promisekeeper.cli demo --json | python -c '
import json, sys
d = json.load(sys.stdin)
assert d["decision"] == "block", d                      # gold EU order breaches the 3-day SLA
assert d["memories_used"] == 7 and not d["degraded_recall"], d
assert d["alternatives"] and d["alternatives"][0]["decision"] == "allow", d   # evidence-backed fix offered
print("ok:", d["decision"], d["total_value"], "->", d["alternatives"][0])'

echo "AUDIT OK: tests passed, seeded demo blocked the SLA breach and offered an alternative, no prohibited word, no tracked .env."
