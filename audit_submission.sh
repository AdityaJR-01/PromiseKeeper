#!/bin/bash
echo "--- Running Pre-Submission Audit ---"
if grep -rniE 'hack-?a-?thon' README.md docs/ content/ 2>/dev/null; then
    echo "FAIL: Prohibited event word found. Clean your documents[cite: 2]."
    exit 1
fi
if git ls-files | grep -E '(^|/)\.env$'; then
    echo "FAIL: .env file is tracked by Git. Untrack it[cite: 2]."
    exit 1
fi
echo "AUDIT OK: You are clear to push."
