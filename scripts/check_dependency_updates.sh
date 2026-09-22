#!/usr/bin/env bash
# ==============================================================================
# Script: check_dependency_updates.sh
# Purpose: Comprehensive Outdated & Security Audit Tool for dgx-spark-toolkit
#          (Python backend + React frontend) adhering to CCBA 3-Tier Architecture.
# Usage:
#   ./scripts/check_dependency_updates.sh           # Run all checks
#   ./scripts/check_dependency_updates.sh --outdated # Check outdated only
#   ./scripts/check_dependency_updates.sh --audit    # Check security vulnerabilities only
# ==============================================================================

set -euo pipefail

# Determine repository root via relative script path (avoid hardcoded absolute paths)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

RAG_DIR="${ROOT_DIR}/services/rag-service"
FRONTEND_DIR="${ROOT_DIR}/services/frontend"

# Color constants
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

MODE="all"
if [[ $# -gt 0 ]]; then
    case "$1" in
        --outdated)
            MODE="outdated"
            ;;
        --audit)
            MODE="audit"
            ;;
        --all)
            MODE="all"
            ;;
        --help|-h)
            echo "Usage: $0 [--all | --outdated | --audit]"
            echo "  --all       Run both outdated version check and security audit (default)"
            echo "  --outdated  Check outdated dependencies (Python backend + React frontend)"
            echo "  --audit     Run vulnerability audit (pip-audit + npm audit)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use '$0 --help' for usage."
            exit 1
            ;;
    esac
fi

echo -e "${BOLD}${CYAN}======================================================================${NC}"
echo -e "${BOLD}${CYAN} 📦 DGX Spark Toolkit — Dependency Check & Security Audit             ${NC}"
echo -e "${BOLD}${CYAN}======================================================================${NC}"
echo -e "Target Root: ${ROOT_DIR}"
echo -e "Mode:        ${BOLD}${MODE}${NC}"
echo ""

# ------------------------------------------------------------------------------
# 1. OUTDATED CHECK
# ------------------------------------------------------------------------------
if [[ "$MODE" == "all" || "$MODE" == "outdated" ]]; then
    echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"
    echo -e "${BOLD}${BLUE}[1/2] Checking Outdated Dependencies                                  ${NC}"
    echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"

    # 1.1 Python Backend
    echo -e "\n${BOLD}>>> Python Backend (services/rag-service)${NC}"
    PYTHON_BIN=""
    if [[ -x "${RAG_DIR}/venv/bin/python" ]]; then
        PYTHON_BIN="${RAG_DIR}/venv/bin/python"
    elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
        PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
    elif command -v python3 &>/dev/null; then
        PYTHON_BIN="$(command -v python3)"
    fi

    if command -v uv &>/dev/null && [[ -n "$PYTHON_BIN" ]]; then
        echo -e "Running ${CYAN}uv pip list --outdated${NC} using: ${PYTHON_BIN}"
        echo -e "${YELLOW}Architectural Tier Guidance:${NC}"
        echo -e "  🟢 ${GREEN}Tier A (Fast-track App/Utils):${NC} fastapi, uvicorn, pydantic, requests, pyarrow"
        echo -e "  🟡 ${YELLOW}Tier B (Staged DB Clients):${NC}   pymilvus, neo4j, redis (must align with docker-compose server versions)"
        echo -e "  🔴 ${RED}Tier C (PINNED Hardware):${NC}    torch, torchvision, vllm, triton, nvidia-* (DO NOT BUMP via PyPI!)"
        echo ""
        # Run uv pip list and allow exit code 0
        uv pip list --outdated --python "$PYTHON_BIN" || true
    else
        echo -e "${YELLOW}Warning: 'uv' or Python environment not found. Skipping backend outdated check.${NC}"
    fi

    # 1.2 Frontend
    echo -e "\n${BOLD}>>> React Frontend (services/frontend)${NC}"
    if command -v npm &>/dev/null && [[ -d "${FRONTEND_DIR}/node_modules" ]]; then
        echo -e "Running ${CYAN}npm outdated${NC} in ${FRONTEND_DIR}..."
        (cd "${FRONTEND_DIR}" && npm outdated || true)
        echo -e "${YELLOW}Note: Do NOT run 'npm audit fix --force' as it forces downgrade of react-force-graph.${NC}"
    else
        echo -e "${YELLOW}Warning: npm or node_modules not found in ${FRONTEND_DIR}. Skipping frontend outdated check.${NC}"
    fi
    echo ""
fi

# ------------------------------------------------------------------------------
# 2. SECURITY AUDIT
# ------------------------------------------------------------------------------
if [[ "$MODE" == "all" || "$MODE" == "audit" ]]; then
    echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"
    echo -e "${BOLD}${BLUE}[2/2] Running Security Vulnerability Audits                          ${NC}"
    echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"

    AUDIT_ERRORS=0

    APP_LOCK_WARNINGS=0

    # 2.1 Backend CI Requirements Audit
    echo -e "\n${BOLD}>>> [Backend CI] Auditing requirements-ci.txt${NC}"
    if [[ -f "${RAG_DIR}/requirements-ci.txt" ]]; then
        if command -v uvx &>/dev/null; then
            echo -e "Executing: ${CYAN}uvx pip-audit -r ${RAG_DIR}/requirements-ci.txt${NC}"
            if uvx pip-audit -r "${RAG_DIR}/requirements-ci.txt"; then
                echo -e "  Status: ${GREEN}✅ CLEAN (No known vulnerabilities found in CI dependencies)${NC}"
            else
                echo -e "  Status: ${RED}❌ VULNERABILITIES DETECTED in requirements-ci.txt${NC}"
                AUDIT_ERRORS=$((AUDIT_ERRORS + 1))
            fi
        else
            echo -e "${YELLOW}'uvx' not found. Skipping pip-audit on requirements-ci.txt.${NC}"
        fi
    fi

    # 2.2 Backend Full App Lockfile Audit (Informational/Warning)
    echo -e "\n${BOLD}>>> [Backend App] Auditing requirements-app.lock${NC}"
    if [[ -f "${RAG_DIR}/requirements-app.lock" ]]; then
        if command -v uvx &>/dev/null; then
            echo -e "Executing: ${CYAN}uvx pip-audit -r ${RAG_DIR}/requirements-app.lock${NC}"
            if uvx pip-audit -r "${RAG_DIR}/requirements-app.lock"; then
                echo -e "  Status: ${GREEN}✅ CLEAN (No known vulnerabilities found in App Lockfile)${NC}"
            else
                echo -e "  Status: ${YELLOW}⚠️  Advisories found in full app lockfile. Review Tier A/B upgrade paths.${NC}"
                APP_LOCK_WARNINGS=$((APP_LOCK_WARNINGS + 1))
            fi
        fi
    fi

    # 2.3 Frontend Production Audit
    echo -e "\n${BOLD}>>> [Frontend Production] Auditing npm packages (--omit=dev --audit-level=critical)${NC}"
    if command -v npm &>/dev/null && [[ -f "${FRONTEND_DIR}/package.json" ]]; then
        echo -e "Executing: ${CYAN}npm audit --omit=dev --audit-level=critical in ${FRONTEND_DIR}${NC}"
        if (cd "${FRONTEND_DIR}" && npm audit --omit=dev --audit-level=critical); then
            echo -e "  Status: ${GREEN}✅ CLEAN (No critical vulnerabilities in production frontend dependencies)${NC}"
        else
            echo -e "  Status: ${RED}❌ CRITICAL VULNERABILITIES DETECTED in production frontend dependencies${NC}"
            AUDIT_ERRORS=$((AUDIT_ERRORS + 1))
        fi
    fi

    echo ""
    echo -e "${BOLD}${CYAN}======================================================================${NC}"
    if [[ $AUDIT_ERRORS -eq 0 && $APP_LOCK_WARNINGS -eq 0 ]]; then
        echo -e "${BOLD}${GREEN} 🎉 Security Audit Passed: All production and lockfile checks clean!   ${NC}"
    elif [[ $AUDIT_ERRORS -eq 0 ]]; then
        echo -e "${BOLD}${YELLOW} ⚠️  CI Gates Passed, but App Lockfile has active security advisories. ${NC}"
        echo -e "${YELLOW}    (Note: pillow locked by surya-ocr; review Tier A/B bump roadmap)  ${NC}"
    else
        echo -e "${BOLD}${RED} ❌ Security Audit Failed: ${AUDIT_ERRORS} critical check(s) reported issues.      ${NC}"
    fi
    echo -e "${BOLD}${CYAN}======================================================================${NC}"

    if [[ $AUDIT_ERRORS -gt 0 ]]; then
        exit 1
    fi
fi

echo -e "\n${BOLD}${GREEN}Done!${NC}\n"
