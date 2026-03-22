#!/usr/bin/env bash
# Pre-flight checks for GitHub CLI operations.
# Run before automated gh/workflow commands to catch missing tools or permissions early.
set -euo pipefail

PASS=0
FAIL=0

check() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "[PASS] $label"
        ((PASS++))
    else
        echo "[FAIL] $label"
        ((FAIL++))
    fi
}

echo "=== GitHub CLI Pre-flight Checks ==="
check "gh CLI installed"       which gh
check "gh authenticated"       gh auth status
check "gh repo accessible"     gh repo view --json name

echo ""
echo "Result: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
