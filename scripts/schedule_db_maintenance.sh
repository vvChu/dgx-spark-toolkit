#!/usr/bin/env bash
# ==============================================================================
# LiteLLM Database Scheduled Maintenance Runner
# ==============================================================================
# Runs weekly/monthly database cleanup:
# 1. Archives old spend logs (>30 days) to archives/spendlogs/*.jsonl.gz
# 2. Performs chunked CTE deletion (5,000 rows/batch) without table locks
# 3. Executes non-blocking VACUUM ANALYZE to reclaim disk space
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/db_maintenance.log"

mkdir -p "$LOG_DIR"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Starting DB Maintenance ===" >> "$LOG_FILE"

cd "$PROJECT_ROOT"
if python3 "$SCRIPT_DIR/prune_spend_logs.py" --retention-days 30 --health-retention-days 7 --vacuum >> "$LOG_FILE" 2>&1; then
    echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] DB Maintenance Succeeded ===" >> "$LOG_FILE"
    exit 0
else
    echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] DB Maintenance FAILED ===" >> "$LOG_FILE"
    exit 1
fi
