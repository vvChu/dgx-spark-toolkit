#!/usr/bin/env bash
# Smoke Test Live Script for RAG Service (ADR-0044 compliant)
# Tests core live API endpoints: /health, /stats, and /search (POST)
# Exit code 0 indicates all checks returned HTTP 200 OK.

set -euo pipefail

BASE_URL="${RAG_SERVICE_URL:-http://localhost:${RAG_PORT:-8005}}"
TIMEOUT_SECONDS=120
FAILED_TESTS=0

echo "================================================================"
echo "🧪 RAG SERVICE LIVE SMOKE TEST"
echo "Target Base URL: ${BASE_URL}"
echo "================================================================"

test_endpoint() {
    local method="$1"
    local path="$2"
    local data="$3"
    local description="$4"

    echo -n "Checking ${description} (${method} ${path})... "

    local response
    local http_code
    local body

    if [ "${method}" = "GET" ]; then
        response=$(curl -s -S --max-time "${TIMEOUT_SECONDS}" \
            -w "\n%{http_code}" \
            "${BASE_URL}${path}" 2>&1) || {
            echo "FAILED (Network/Connection error)"
            echo "Details: ${response}"
            FAILED_TESTS=$((FAILED_TESTS + 1))
            return 1
        }
    else
        response=$(curl -s -S --max-time "${TIMEOUT_SECONDS}" \
            -X POST \
            -H "Content-Type: application/json" \
            -d "${data}" \
            -w "\n%{http_code}" \
            "${BASE_URL}${path}" 2>&1) || {
            echo "FAILED (Network/Connection error)"
            echo "Details: ${response}"
            FAILED_TESTS=$((FAILED_TESTS + 1))
            return 1
        }
    fi

    http_code=$(echo "${response}" | tail -n 1)
    body=$(echo "${response}" | sed '$d')

    if [ "${http_code}" = "200" ]; then
        echo "✅ PASS (HTTP 200)"
        local snippet
        snippet=$(echo "${body}" | head -c 120)
        echo "   Response: ${snippet}..."
        return 0
    else
        echo "❌ FAIL (HTTP ${http_code})"
        echo "   Body: ${body}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi
}

echo ""
test_endpoint "GET" "/health" "" "Health Check" || true
test_endpoint "GET" "/stats" "" "System Stats" || true
test_endpoint "POST" "/search" '{"query": "luat xay dung", "limit": 2, "use_reranker": false}' "Search Endpoint (Fast Hybrid)" || true
test_endpoint "POST" "/search" '{"query": "luat xay dung", "limit": 2}' "Search Endpoint (Full Pipeline)" || true

echo ""
echo "================================================================"
if [ "${FAILED_TESTS}" -eq 0 ]; then
    echo "🎉 ALL LIVE SMOKE TESTS PASSED (100% Green)"
    echo "================================================================"
    exit 0
else
    echo "🚨 SMOKE TESTS FAILED (${FAILED_TESTS} failed test(s))"
    echo "================================================================"
    exit 1
fi
