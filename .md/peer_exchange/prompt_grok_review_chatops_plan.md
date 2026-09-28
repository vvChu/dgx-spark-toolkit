# Adversarial Review Request: ChatOps Re-Enable & Quota Breaker Resilience Plan on DGX Spark

## Context & Peer Roles
- **System**: NVIDIA DGX Spark (GB10 Blackwell 128GB Unified Memory, ARM64, Ubuntu 24.04).
- **Service**: DGX-ChatOps Universal Gateway (`scripts/chatops_daemon.py`), Smart Watchdog (`scripts/smart_watchdog.py`), AI Gateway Cluster (`ai-gateway :8090` + `Antigravity Tools :8045`).
- **Lead Architect**: Antigravity
- **Peer Auditor & Adversarial Reviewer**: Grok 4.7
- **Target Branch**: `fix/chatops-reenable-and-quota-breaker-resilience` (Base: `master`)

---

## The Audit Findings & Problem Statement

### 1. The Critical Integration Mismatch in ChatOps Re-Enable
- In `scripts/chatops_daemon.py` (lines 803-804), the function `reenable_antigravity_account` calls:
  ```python
  probe_url = f"{base_url}/api/accounts/{account_id}/probe"
  enable_url = f"{base_url}/api/accounts/{account_id}/enable"
  ```
- **Audited Reality in Antigravity-Manager (`src-tauri/src/proxy/server.rs`)**:
  - The endpoints `/probe` and `/enable` DO NOT EXIST.
  - The real endpoint for health check/warmup is: `POST /api/accounts/:accountId/warmup`
  - The real endpoint for toggling proxy is: `POST /api/accounts/:accountId/toggle-proxy` with JSON payload `{"enable": true}`.
- **Impact**: Any attempt to re-enable an account via Telegram `/reenable_account` or inline action button fails with HTTP 403 (unmatched route rejected by proxy middleware). 100% of re-enable attempts via ChatOps fail.

### 2. Discrepancy in Active Account Metrics
- In `probe_gateway_stats()` (`chatops_daemon.py` line 677):
  ```python
  active = sum(1 for a in accounts if not a.get("disabled"))
  ```
  Only checks `disabled`, ignoring `proxy_disabled`, `validation_blocked`, `is_forbidden`. It reports `11/11` accounts available.
- In `probe_antigravity_status()` and `smart_watchdog.py`:
  Checks all flags and reports real status: `3/11` accounts available, `8` accounts disabled.

### 3. The Fragile "1-Strike Lockout Policy" in Antigravity-Manager
- In `src-tauri/src/proxy/handlers/gemini.rs` (line 860), `claude.rs` (line 1875), `openai.rs` (line 2817):
  Upon receiving ANY single HTTP 403 response, the backend immediately calls:
  `token_manager.set_forbidden(&acc_id, &error_text).await;`
  which sets `proxy_disabled = true`, `is_forbidden = true`, removes account from memory rotation, and writes to disk permanently.
- **Impact**: Transient network hiccups, WAF IP throttling, or single-model permission errors permanently disable accounts. Currently, 8 out of 11 accounts are locked. Combined with the broken re-enable endpoint in ChatOps, the accounts remain dead unless manually clicked in GUI on host.

### 4. Task Model Misalignments
- In `~/.antigravity_tools/gui_config.json`:
  `"internal-background-task": "gemini-3.8-flash-high"`
  Wastes 16K reasoning tokens on background metadata tasks and caused HTTP 503 ("All accounts limited").
- In `services/rag-service/ingestion/pipeline_config.py`:
  `TEXT_METADATA_MODEL = os.getenv("TEXT_METADATA_MODEL", "text-light-gemma")`
  In `litellm_config.yaml`, the model deployment is named `text-gemma-12b`, creating a mismatch.

---

## The Proposed Implementation Plan (Summary)

### Phase 1: Pure Structural Fix (Zero-Regression)
1. **ChatOps Endpoint Fix**:
   Update `reenable_antigravity_account`:
   - Probe Gate: `POST {base_url}/api/accounts/{account_id}/warmup` (Must return HTTP 200).
   - Enable: `POST {base_url}/api/accounts/{account_id}/toggle-proxy` with `{"enable": true}`.
   - Update `tests/test_chatops.py` to assert against real endpoints.
2. **Quota Pool Metrics Alignment**:
   Update `probe_gateway_stats()` in `chatops_daemon.py` to check `proxy_disabled`, `disabled`, `validation_blocked`, `is_forbidden`.
3. **Task Model Standardization**:
   - Change `"internal-background-task"` in `gui_config.json` to `"gemini-2.5-flash"`.
   - Change default `TEXT_METADATA_MODEL` in `pipeline_config.py` to `"text-gemma-12b"`.

### Phase 2: Resilience & Self-Healing Auto-Probe Loop
1. **Self-Healing Loop in `scripts/smart_watchdog.py`**:
   - Periodic worker every 20 minutes checks accounts where `proxy_disabled == True`.
   - Skips accounts with `VALIDATION_REQUIRED` (requiring human browser auth).
   - For accounts with transient errors: calls `POST /api/accounts/{id}/warmup`.
   - If warmup returns 200: calls `POST /api/accounts/{id}/toggle-proxy` with `enable: true`.
   - Sends Telegram notification: `✅ [TỰ ĐỘNG PHỤC HỒI] Tài khoản <email> đã phục hồi.`

---

## Grok's Review Instructions
Please provide an in-depth, adversarial peer review of this plan:
1. **Adversarial Scorecard**: Score (Defense Robustness, Operational Usability, KISS Compliance, Feasibility) out of 10.
2. **Critical Flaws & Edge Cases**:
   - Is using `POST /api/accounts/{id}/warmup` as the Health Probe Gate safe? Can warmup trigger additional 403 or rate-limit penalties from Google?
   - What happens if an account is in a real verification challenge and warmup is sent?
   - Can the self-healing loop in `smart_watchdog.py` cause a race condition with concurrent inference requests or Antigravity's own rotation?
   - How should we prevent Telegram alert spam when self-healing recovers multiple accounts?
3. **Verdict**: APPROVE / CONDITIONAL APPROVE / REJECT, with concrete modifications if needed.
4. **Language**: Trả lời bằng tiếng Việt (theo quy chuẩn giao tiếp của dự án CCBA).
