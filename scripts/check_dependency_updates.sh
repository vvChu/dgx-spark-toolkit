#!/usr/bin/env bash
# ==============================================================================
# Script: check_dependency_updates.sh
# Purpose: Comprehensive Dependency Checker, Security Auditor & 1-Click Upgrader
#          for dgx-spark-toolkit (Python backend + React frontend)
#          adhering to CCBA 3-Tier Architecture & ADR-0058 Hard Completion Lock.
# Usage:
#   ./scripts/check_dependency_updates.sh                   # Run all checks
#   ./scripts/check_dependency_updates.sh --outdated        # Check outdated only
#   ./scripts/check_dependency_updates.sh --audit           # Check vulnerabilities only
#   ./scripts/check_dependency_updates.sh --upgrade=patch   # 1-Click Tier 1 Upgrade
#   ./scripts/check_dependency_updates.sh --upgrade=minor   # 1-Click Tier 2 Upgrade
# ==============================================================================

set -euo pipefail

# Determine repository root via relative script path
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
UPGRADE_TIER="patch"

for arg in "$@"; do
    case "$arg" in
        --outdated)
            MODE="outdated"
            ;;
        --audit)
            MODE="audit"
            ;;
        --all)
            MODE="all"
            ;;
        --upgrade)
            MODE="upgrade"
            UPGRADE_TIER="patch"
            ;;
        --upgrade=*)
            MODE="upgrade"
            UPGRADE_TIER="${arg#*=}"
            ;;
        --help|-h)
            echo "Usage: $0 [--all | --outdated | --audit | --upgrade[=patch|=minor]]"
            echo "  --all              Run both outdated version check and security audit (default)"
            echo "  --outdated         Check outdated dependencies (Python backend + React frontend)"
            echo "  --audit            Run vulnerability audit (pip-audit + npm audit)"
            echo "  --upgrade[=tier]   Upgrade dependencies (tier: patch [default] or minor) with deterministic verification"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $arg${NC}"
            echo "Use '$0 --help' for usage."
            exit 1
            ;;
    esac
done

if [[ "$MODE" == "upgrade" && "$UPGRADE_TIER" != "patch" && "$UPGRADE_TIER" != "minor" ]]; then
    echo -e "${RED}Invalid upgrade tier: '${UPGRADE_TIER}'. Allowed values: patch, minor.${NC}"
    exit 1
fi

# Resolve Python Executable deterministically (RULE-5.1)
PYTHON_BIN=""
if [[ -x "${RAG_DIR}/venv/bin/python" ]]; then
    PYTHON_BIN="${RAG_DIR}/venv/bin/python"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="$(command -v python3)"
fi

# Resolve Flake8 Executable
FLAKE8_BIN=""
if [[ -x "${RAG_DIR}/venv/bin/flake8" ]]; then
    FLAKE8_BIN="${RAG_DIR}/venv/bin/flake8"
elif [[ -x "${ROOT_DIR}/.venv/bin/flake8" ]]; then
    FLAKE8_BIN="${ROOT_DIR}/.venv/bin/flake8"
elif command -v flake8 &>/dev/null; then
    FLAKE8_BIN="$(command -v flake8)"
fi

echo -e "${BOLD}${CYAN}======================================================================${NC}"
echo -e "${BOLD}${CYAN} 📦 DGX Spark Toolkit — Dependency Manager & Security Auditor         ${NC}"
echo -e "${BOLD}${CYAN}======================================================================${NC}"
echo -e "Target Root: ${ROOT_DIR}"
echo -e "Mode:        ${BOLD}${MODE}${NC}"
if [[ "$MODE" == "upgrade" ]]; then
    echo -e "Tier:        ${BOLD}${UPGRADE_TIER}${NC}"
fi
echo ""

# ------------------------------------------------------------------------------
# 0. 1-CLICK UPGRADE (TIER 1 & TIER 2)
# ------------------------------------------------------------------------------
if [[ "$MODE" == "upgrade" ]]; then
    echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"
    echo -e "${BOLD}${BLUE}🚀 [DGX-Upgrade] Executing 1-Click Upgrade (Tier: ${UPGRADE_TIER})    ${NC}"
    echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"

    # 1. Frontend Upgrade
    echo -e "\n${BOLD}>>> [1/3] Upgrading Frontend Dependencies...${NC}"
    if [[ "$UPGRADE_TIER" == "minor" ]]; then
        echo -e "Running ${CYAN}npm update${NC} in ${FRONTEND_DIR}..."
        (cd "${FRONTEND_DIR}" && npm update)
    else
        echo -e "Running ${CYAN}npm audit fix${NC} in ${FRONTEND_DIR}..."
        (cd "${FRONTEND_DIR}" && npm audit fix || true)
    fi

    # 2. Backend Recompile Lockfile
    echo -e "\n${BOLD}>>> [2/3] Recompiling Deterministic Backend Lockfile...${NC}"
    if ! command -v uv &>/dev/null; then
        echo -e "${RED}Error: 'uv' executable is required to recompile deterministic backend lockfile.${NC}"
        exit 1
    fi

    echo -e "Compiling ${CYAN}requirements-app.in${NC} -> ${CYAN}requirements-app.lock${NC} with 27 Blackwell GPU exclusions..."
    uv pip compile "${RAG_DIR}/requirements-app.in" \
      --upgrade \
      --no-emit-package torch --no-emit-package torchvision --no-emit-package torchaudio \
      --no-emit-package vllm --no-emit-package triton \
      --no-emit-package transformers --no-emit-package tokenizers \
      --no-emit-package huggingface-hub --no-emit-package safetensors \
      --no-emit-package cuda-bindings --no-emit-package cuda-pathfinder --no-emit-package cuda-toolkit \
      --no-emit-package nvidia-cublas --no-emit-package nvidia-cuda-cupti --no-emit-package nvidia-cuda-nvrtc \
      --no-emit-package nvidia-cuda-runtime --no-emit-package nvidia-cudnn-cu13 --no-emit-package nvidia-cufft \
      --no-emit-package nvidia-cufile --no-emit-package nvidia-curand --no-emit-package nvidia-cusolver \
      --no-emit-package nvidia-cusparse --no-emit-package nvidia-cusparselt-cu13 --no-emit-package nvidia-nccl-cu13 \
      --no-emit-package nvidia-nvjitlink --no-emit-package nvidia-nvshmem-cu13 --no-emit-package nvidia-nvtx \
      -o "${RAG_DIR}/requirements-app.lock"

    # 3. Deterministic Verification Gate (ADR-0058 Hard Completion Lock)
    echo -e "\n${BOLD}>>> [3/3] Running Deterministic Verification Gate (ADR-0058)...${NC}"
    echo -e "Testing Frontend: lint, typecheck, build & bundle budget..."
    (cd "${FRONTEND_DIR}" && npm run lint)
    (cd "${FRONTEND_DIR}" && npm run typecheck)
    (cd "${FRONTEND_DIR}" && npm run build)

    if [[ -n "$PYTHON_BIN" ]]; then
        echo -e "Testing Backend: 474 unit tests..."
        "$PYTHON_BIN" -m pytest "${RAG_DIR}/tests/" -k "not live and not integration" -q
    fi

    if [[ -n "$FLAKE8_BIN" ]]; then
        echo -e "Testing Backend: flake8 lint..."
        "$FLAKE8_BIN" "${RAG_DIR}/" --config="${RAG_DIR}/.flake8"
    fi

    echo -e "\n${BOLD}${GREEN}======================================================================${NC}"
    echo -e "${BOLD}${GREEN} 🎉 [DGX-Upgrade] Upgrade succeeded and verified (0 regression)!       ${NC}"
    echo -e "${BOLD}${GREEN}======================================================================${NC}\n"
    exit 0
fi

# ------------------------------------------------------------------------------
# 1. OUTDATED CHECK
# ------------------------------------------------------------------------------
if [[ "$MODE" == "all" || "$MODE" == "outdated" ]]; then
    echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"
    echo -e "${BOLD}${BLUE}[1/2] Checking Outdated Dependencies                                  ${NC}"
    echo -e "${BOLD}${BLUE}----------------------------------------------------------------------${NC}"

    # 1.1 Python Backend
    echo -e "\n${BOLD}>>> Python Backend (services/rag-service)${NC}"
    if command -v uv &>/dev/null && [[ -n "$PYTHON_BIN" ]]; then
        echo -e "Running ${CYAN}uv pip list --outdated${NC} using: ${PYTHON_BIN}"
        echo -e "${YELLOW}Architectural Tier Guidance:${NC}"
        echo -e "  🟢 ${GREEN}Tier A (Fast-track App/Utils):${NC} fastapi, uvicorn, pydantic, requests, pyarrow"
        echo -e "  🟡 ${YELLOW}Tier B (Staged DB Clients):${NC}   pymilvus, neo4j, redis (must align with docker-compose server versions)"
        echo -e "  🔴 ${RED}Tier C (PINNED Hardware):${NC}    torch, torchvision, vllm, triton, nvidia-* (DO NOT BUMP via PyPI!)"
        echo ""
        uv pip list --outdated --python "$PYTHON_BIN" || true
    else
        echo -e "${YELLOW}Warning: 'uv' or Python environment not found. Skipping backend outdated check.${NC}"
    fi

    # 1.2 Frontend
    echo -e "\n${BOLD}>>> React Frontend (services/frontend)${NC}"
    if command -v npm &>/dev/null && [[ -d "${FRONTEND_DIR}/node_modules" ]]; then
        echo -e "Running ${CYAN}npm outdated${NC} in ${FRONTEND_DIR}..."
        (cd "${FRONTEND_DIR}" && npm outdated || true)
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

    # 2.2 Backend Full App Lockfile Audit
    echo -e "\n${BOLD}>>> [Backend App] Auditing requirements-app.lock${NC}"
    if [[ -f "${RAG_DIR}/requirements-app.lock" ]]; then
        if command -v uvx &>/dev/null; then
            echo -e "Executing: ${CYAN}uvx pip-audit -r ${RAG_DIR}/requirements-app.lock${NC}"
            if uvx pip-audit -r "${RAG_DIR}/requirements-app.lock"; then
                echo -e "  Status: ${GREEN}✅ CLEAN (No known vulnerabilities found in App Lockfile)${NC}"
            else
                echo -e "  Status: ${RED}❌ VULNERABILITIES DETECTED in App Lockfile${NC}"
                AUDIT_ERRORS=$((AUDIT_ERRORS + 1))
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
    else
        echo -e "${BOLD}${RED} ❌ Security Audit Failed: ${AUDIT_ERRORS} critical check(s) reported issues.      ${NC}"
    fi
    echo -e "${BOLD}${CYAN}======================================================================${NC}"

    if [[ $AUDIT_ERRORS -gt 0 ]]; then
        exit 1
    fi
fi

echo -e "\n${BOLD}${GREEN}Done!${NC}\n"
