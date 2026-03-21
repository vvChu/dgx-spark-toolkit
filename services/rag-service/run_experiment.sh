#!/bin/bash
# Autoresearch experiment runner
# Usage: ./run_experiment.sh "description of change"
#
# Workflow:
#   1. Apply pipeline.py fixes to exports
#   2. Run comprehensive audit
#   3. Parse results with evaluate.py
#   4. If score improved → keep, else → revert

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="/home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml"
SERVICE="rag-service"

DESC="${1:-unnamed_experiment}"

echo "═══════════════════════════════════════════════════"
echo "  AUTORESEARCH EXPERIMENT: $DESC"
echo "═══════════════════════════════════════════════════"

# Step 1: Revert to clean baseline first
echo "[1/4] Reverting to clean baseline..."
docker compose -f "$COMPOSE_FILE" exec "$SERVICE" python3 pipeline.py --revert 2>/dev/null || true

# Step 2: Apply current pipeline.py fixes
echo "[2/4] Applying pipeline.py fixes..."
docker compose -f "$COMPOSE_FILE" exec "$SERVICE" python3 pipeline.py --apply

# Step 3: Run audit
echo "[3/4] Running comprehensive audit..."
docker compose -f "$COMPOSE_FILE" exec "$SERVICE" python3 evaluate.py "$DESC"

# Step 4: Decision (manual for now - evaluate.py logs to results.tsv)
echo "[4/4] Results logged to results.tsv"
echo ""
echo "To revert: docker compose -f $COMPOSE_FILE exec $SERVICE python3 pipeline.py --revert"
