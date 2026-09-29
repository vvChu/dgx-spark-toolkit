"""Smart Watchdog daemon for DGX Spark infrastructure.

Monitors Docker containers, local vLLM, AI Gateway, Antigravity Tools,
and sends real-time incident alerts and a daily digest via Telegram.
"""

import datetime
import os
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple
try:
    import docker
except ImportError:
    docker = None
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-spark-secure-key-2026")
GATEWAY_PROXY_URL = os.environ.get("GATEWAY_PROXY_URL", "http://127.0.0.1:8045")
GATEWAY_PROXY_KEY = os.environ.get("GATEWAY_PROXY_KEY", "")
GATEWAY_ADMIN_PASSWORD = os.environ.get("GATEWAY_ADMIN_PASSWORD") or GATEWAY_PROXY_KEY

# Cooldown for incident alerts (30 minutes per alert_type)
COOLDOWN_MINUTES = 30
last_alert_time: Dict[str, float] = {}
last_digest_date: Optional[str] = None


# ChatOps Gateway Integration
CHATOPS_GATEWAY_URL = os.environ.get("CHATOPS_GATEWAY_URL", "http://172.21.0.1:8095")  # ccba:allow-raw-ip
CHATOPS_INTERNAL_SECRET = os.environ.get("CHATOPS_INTERNAL_SECRET", "").strip()


def send_telegram_raw(message: str) -> bool:
    """Sends a raw markdown-formatted message to Telegram directly."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing Telegram Credentials!", flush=True)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except requests.RequestException as e:
        print(f"Failed to send Telegram message: {e}", flush=True)
        return False


def notify_chatops(title: str, body: str, actions: Optional[List[Dict[str, Any]]] = None, severity: str = "INFO") -> bool:
    """Dispatches an interactive event to DGX-ChatOps Gateway with fallback to direct Telegram."""
    if CHATOPS_INTERNAL_SECRET and CHATOPS_GATEWAY_URL:
        try:
            payload = {
                "title": title,
                "body": body,
                "severity": severity,
                "actions": actions or [],
            }
            headers = {
                "Content-Type": "application/json",
                "X-ChatOps-Secret": CHATOPS_INTERNAL_SECRET,
            }
            res = requests.post(f"{CHATOPS_GATEWAY_URL}/api/v1/notify", json=payload, headers=headers, timeout=3)
            if res.status_code == 200:
                return True
            print(f"[Watchdog -> ChatOps Gateway Error] HTTP {res.status_code}: {res.text}. Falling back to direct Telegram...", flush=True)
        except Exception as e:
            print(f"[Watchdog -> ChatOps Gateway Error] {e}. Falling back to direct Telegram...", flush=True)
    else:
        print("[Watchdog -> ChatOps Gateway] Secret or Gateway URL unconfigured. Falling back to direct Telegram...", flush=True)

    # Fallback to direct raw Telegram message
    return send_telegram_raw(f"🔔 *{title}*\n\n{body}")


def send_telegram_alert(message: str, alert_type: str) -> None:
    """Sends an incident alert with cooldown protection and interactive action buttons."""
    now = time.time()
    if alert_type in last_alert_time:
        if now - last_alert_time[alert_type] < COOLDOWN_MINUTES * 60:
            return  # Cooldown active

    actions: List[Dict[str, Any]] = []
    if "container_down_" in alert_type:
        svc = alert_type.replace("container_down_", "")
        actions.append({
            "action_id": f"restart_{svc}",
            "label": f"🔄 Khởi Động Lại {svc}",
            "command": "system.container.restart",
            "params": {"service": svc},
        })
    elif alert_type == "vllm_deadlock":
        actions.append({
            "action_id": "restart_qwen36b",
            "label": "🔄 Khởi Động Lại vLLM (Qwen 35B)",
            "command": "system.container.restart",
            "params": {"service": "qwen36b"},
        })

    title = "CẢNH BÁO SỰ CỐ TỪ SMART WATCHDOG"
    if notify_chatops(title, message, actions=actions, severity="WARNING"):
        last_alert_time[alert_type] = now
        print(f"Sent alert for: {alert_type}", flush=True)


def check_docker_containers() -> None:
    """Checks the status of core docker containers."""
    if docker is None:
        print("Docker Python SDK not installed, skipping container check", flush=True)
        return
    try:
        client = docker.from_env()
        core_services = [
            "open-webui",
            "qwen36b",
            "ai-gateway",
            "cloudflared-tunnel",
            "rag-service",
            "milvus-standalone",
            "neo4j-graph",
        ]
        for service in core_services:
            try:
                container = client.containers.get(service)
                if container.status != "running":
                    send_telegram_alert(
                        f"Container `{service}` hiện đang bị dừng (Status: {container.status}). Vui lòng kiểm tra ngay!",
                        f"container_down_{service}",
                    )
            except docker.errors.NotFound:
                pass
    except Exception as e:
        print(f"Docker API Error: {e}", flush=True)


def check_vllm_deadlock() -> None:
    """Probes vLLM engine liveliness and basic inference."""
    try:
        res = requests.get("http://qwen36b:8000/v1/models", timeout=5)
        if res.status_code != 200:
            send_telegram_alert(
                "vLLM (qwen36b) không trả về kết nối ở port 8000! Có thể tiến trình đã sập.",
                "vllm_dead",
            )
            return

        payload = {
            "model": "qwen-local-primary",
            "messages": [{"role": "user", "content": "1"}],
            "max_tokens": 1,
        }
        res = requests.post("http://qwen36b:8000/v1/chat/completions", json=payload, timeout=15)
        if res.status_code != 200:
            send_telegram_alert(
                f"vLLM trả về lỗi HTTP {res.status_code} khi suy luận!",
                "vllm_error",
            )
    except requests.exceptions.Timeout:
        send_telegram_alert(
            "vLLM (Qwen 35B) bị kẹt (Timeout >15s) khi tính toán 1 token! "
            "Engine đang bị Deadlock hoặc OOM. Vui lòng chạy: `docker restart qwen36b`",
            "vllm_deadlock",
        )
    except requests.RequestException:
        pass


def check_ai_gateway() -> None:
    """Probes AI Gateway liveliness and routing."""
    try:
        payload = {
            "model": "rag-core",
            "messages": [{"role": "user", "content": "1"}],
            "max_tokens": 1,
        }
        headers = {"Authorization": f"Bearer {LITELLM_MASTER_KEY}"}
        res = requests.post(
            "http://ai-gateway:4000/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=45,
        )
        if res.status_code == 400:
            send_telegram_alert(
                "AI Gateway trả về lỗi 400 Bad Request! Khả năng cấu hình Model ID hoặc Upstream Proxy sai lệch.",
                "gateway_400",
            )
        elif res.status_code in [502, 503, 504]:
            send_telegram_alert(
                f"AI Gateway báo lỗi Server Error {res.status_code}. Luồng Fallback có thể đang gặp sự cố!",
                "gateway_50x",
            )
    except requests.exceptions.Timeout:
        send_telegram_alert(
            "AI Gateway bị treo hoàn toàn (Timeout >45s) và không thể chuyển hướng Fallback!",
            "gateway_timeout",
        )
    except requests.RequestException:
        pass


def get_proxy_base_url() -> str:
    """Returns normalized Antigravity Tools base URL without /v1 suffix."""
    return GATEWAY_PROXY_URL.rstrip("/").removesuffix("/v1")


def check_antigravity_tools() -> None:
    """Checks Antigravity Tools daemon liveliness on port 8045."""
    base_url = get_proxy_base_url()
    try:
        res = requests.get(f"{base_url}/healthz", timeout=5)
        if res.status_code != 200:
            send_telegram_alert(
                f"Antigravity Tools (`:8045`) phản hồi mã lỗi HTTP {res.status_code}! Tiến trình có thể bị treo.",
                "antigravity_health_error",
            )
    except requests.RequestException as e:
        send_telegram_alert(
            f"Antigravity Tools (`:8045`) mất kết nối hoàn toàn ({e})! Daemon trên server host có thể đã dừng.",
            "antigravity_down",
        )


known_blocked_accounts: Dict[str, float] = {}


def extract_validation_url(account_data: Dict[str, Any]) -> Optional[str]:
    """Extracts Google verification URL from account metadata or error strings."""
    import re
    url = account_data.get("validation_url")
    if url:
        return str(url)

    raw = (
        account_data.get("validation_blocked_reason")
        or account_data.get("proxy_disabled_reason")
        or account_data.get("disabled_reason")
        or (account_data.get("quota") or {}).get("forbidden_reason")
        or ""
    )
    raw_str = str(raw).replace("\\u0026", "&")
    if "accounts.google.com/signin/continue" in raw_str:
        m = re.search(r"https://accounts\.google\.com/signin/continue[^\s\"']+", raw_str)
        if m:
            return m.group(0).rstrip(".,;\"'")
    return None


# --- PHASE 2: RESILIENT AUTO-HEALING HELPERS ---
_healer_memory_first_seen: Dict[str, float] = {}
_healer_memory_attempts: Dict[str, int] = {}
_healer_memory_last_attempt: Dict[str, float] = {}


def _get_redis_client():
    """Gets Redis client connection for watchdog healer state on isolated DB 5."""
    explicit_url = os.getenv("WATCHDOG_REDIS_URL")
    if explicit_url:
        target_url = explicit_url
    else:
        base_url = os.getenv("REDIS_URL", "redis://litellm-redis:6379/5")
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(base_url)
            target_url = urllib.parse.urlunparse(parsed._replace(path="/5"))
        except Exception:
            target_url = "redis://litellm-redis:6379/5"
    try:
        import redis
        return redis.Redis.from_url(target_url, socket_timeout=2)
    except Exception:
        return None


def get_account_lockout_info(acc_id: str) -> Tuple[float, int, float]:
    """Retrieves (first_seen_time, attempts_24h, last_attempt_time) for an account."""
    r = _get_redis_client()
    now = time.time()
    fs_val, att_val, la_val = None, None, None
    if r:
        try:
            fs_val = r.get(f"watchdog:healer:first_seen:{acc_id}")
            att_val = r.get(f"watchdog:healer:attempts:{acc_id}")
            la_val = r.get(f"watchdog:healer:last_attempt:{acc_id}")
        except Exception:
            pass

    if fs_val is not None:
        first_seen = float(fs_val)
    elif acc_id in _healer_memory_first_seen:
        first_seen = _healer_memory_first_seen[acc_id]
    else:
        first_seen = now

    attempts = int(att_val) if att_val is not None else _healer_memory_attempts.get(acc_id, 0)
    last_attempt = float(la_val) if la_val is not None else _healer_memory_last_attempt.get(acc_id, 0.0)
    return first_seen, attempts, last_attempt


def record_account_first_seen(acc_id: str) -> None:
    """Records the initial lockout timestamp if not already tracked."""
    now = time.time()
    recorded_ts = now
    r = _get_redis_client()
    if r:
        try:
            if not r.set(f"watchdog:healer:first_seen:{acc_id}", str(now), nx=True, ex=604800):
                val = r.get(f"watchdog:healer:first_seen:{acc_id}")
                if val:
                    recorded_ts = float(val)
        except Exception:
            pass
    if acc_id not in _healer_memory_first_seen:
        _healer_memory_first_seen[acc_id] = recorded_ts


def record_healing_attempt(acc_id: str) -> None:
    """Records a healing attempt incrementing 24h attempt counter."""
    now = time.time()
    r = _get_redis_client()
    if r:
        try:
            p = r.pipeline()
            p.incr(f"watchdog:healer:attempts:{acc_id}")
            p.expire(f"watchdog:healer:attempts:{acc_id}", 86400)  # 24h
            p.set(f"watchdog:healer:last_attempt:{acc_id}", str(now), ex=86400)
            p.execute()
            return
        except Exception:
            pass
    _healer_memory_attempts[acc_id] = _healer_memory_attempts.get(acc_id, 0) + 1
    _healer_memory_last_attempt[acc_id] = now


def clear_account_healer_state(acc_id: str) -> None:
    """Clears healer tracking state upon successful recovery."""
    r = _get_redis_client()
    if r:
        try:
            r.delete(
                f"watchdog:healer:first_seen:{acc_id}",
                f"watchdog:healer:attempts:{acc_id}",
                f"watchdog:healer:last_attempt:{acc_id}",
            )
        except Exception:
            pass
    _healer_memory_first_seen.pop(acc_id, None)
    _healer_memory_attempts.pop(acc_id, None)
    _healer_memory_last_attempt.pop(acc_id, None)


def is_account_blocked(acc: Dict[str, Any]) -> bool:
    """Determines if an account is in a blocked/non-working state.

    Checks 4 canonical flags:
    1. proxy_disabled: True (manually or breaker disabled)
    2. disabled: True (system disabled)
    3. validation_blocked: True (Google browser challenge required)
    4. quota.is_forbidden: True (Google 403 Forbidden quota exhaustion)
    """
    if not isinstance(acc, dict):
        return True
    if acc.get("proxy_disabled") or acc.get("disabled") or acc.get("validation_blocked"):
        return True
    quota_obj = acc.get("quota")
    if isinstance(quota_obj, dict) and quota_obj.get("is_forbidden"):
        return True
    return False


def quota_probe_allows_toggle(payload: object) -> bool:
    """Strictly evaluates if a quota probe payload authorizes proxy reactivation.

    Rules:
    1. payload must be a non-empty dict.
    2. Sources examined: root payload, and nested payload["quota"] if dict.
    3. If ANY source has "is_forbidden" with True or non-bool -> reject (False).
    4. Must encounter AT LEAST ONE "is_forbidden" that is explicitly boolean False.
    5. Empty payload, missing key, corrupted structure -> reject (False).
    """
    if not isinstance(payload, dict) or not payload:
        return False
    sources = [payload]
    nested = payload.get("quota")
    if isinstance(nested, dict):
        sources.append(nested)
    seen_false = False
    for source in sources:
        if "is_forbidden" not in source:
            continue
        flag = source["is_forbidden"]
        if flag is True or not isinstance(flag, bool):
            return False
        seen_false = True
    return seen_false


def is_eligible_for_auto_heal(account: Dict[str, Any]) -> bool:
    """Checks whether an account can safely undergo automated health probe healing.

    Enforces strict Zero-Upstream-Challenge invariant:
    - No validation URL
    - Not validation_blocked
    - Not globally disabled
    - No challenge/manual block reasons.
    """
    if account.get("validation_url") or extract_validation_url(account):
        return False
    if account.get("validation_blocked"):
        return False
    if account.get("disabled"):
        return False

    raw_reason = str(
        account.get("disabled_reason")
        or account.get("proxy_disabled_reason")
        or account.get("validation_blocked_reason")
        or (account.get("quota") or {}).get("forbidden_reason")
        or ""
    ).lower()

    blocked_keywords = [
        "verify your account",
        "validation_required",
        "invalid_grant",
        "unauthorized_client",
        "manual",
        "disabled manually by user",
    ]
    for kw in blocked_keywords:
        if kw in raw_reason:
            return False

    quota = account.get("quota") or {}
    return bool(account.get("proxy_disabled") or quota.get("is_forbidden"))


def auto_heal_single_candidate(
    accounts: List[Dict[str, Any]],
    base_url: str,
    headers: Dict[str, str],
) -> Optional[str]:
    """Selects and safely attempts to heal at most one eligible account per cycle.

    Enforces:
    - Strict Zero-Upstream-Challenge pre-classification
    - Minimum 60-minute lockout age (cooldown)
    - Max 3 attempts per 24 hours per account
    - 60-minute interval between attempts on the same account
    - 4-stage health probe gate (GET /quota -> check is_forbidden==False -> POST /toggle-proxy)
    """
    now = time.time()
    candidates = []

    for acc in accounts:
        acc_id = str(acc.get("id") or "")
        email = str(acc.get("email") or "unknown")
        if not acc_id:
            continue

        if not is_eligible_for_auto_heal(acc):
            continue

        record_account_first_seen(acc_id)
        first_seen, attempts, last_attempt = get_account_lockout_info(acc_id)
        lockout_age = now - first_seen

        # 1. Lockout age must be at least 60 minutes (3600s)
        if lockout_age < 3600:
            continue

        # 2. Maximum 3 attempts per 24h
        if attempts >= 3:
            continue

        # 3. Minimum 60 minutes between attempts on this account
        if now - last_attempt < 3600:
            continue

        candidates.append({
            "id": acc_id,
            "email": email,
            "attempts": attempts,
            "lockout_age": lockout_age,
        })

    if not candidates:
        return None

    # Rule 5: Multi-Key Deterministic Sorting
    candidates.sort(key=lambda c: (c["attempts"], -round(c["lockout_age"], 2), c["id"]))
    target = candidates[0]
    target_id = target["id"]
    target_email = target["email"]

    print(
        f"[Watchdog Healer] Selected candidate {target_email} ({target_id}) for auto-healing probe "
        f"(Age: {target['lockout_age']:.0f}s, Attempts: {target['attempts']}/3)",
        flush=True,
    )
    record_healing_attempt(target_id)

    quota_url = f"{base_url}/api/accounts/{target_id}/quota"
    toggle_url = f"{base_url}/api/accounts/{target_id}/toggle-proxy"

    try:
        # Stage 2: Quota Probe Gate (GET /quota with timeout 30s)
        q_res = requests.get(quota_url, headers=headers, timeout=30)
        if q_res.status_code != 200:
            print(f"[Watchdog Healer] Quota probe HTTP {q_res.status_code} for {target_email}. Retaining lock.", flush=True)
            return None

        q_data = None
        try:
            q_data = q_res.json() if q_res.content else {}
        except Exception:
            q_data = None

        is_allowed = quota_probe_allows_toggle(q_data)
        if not is_allowed:
            forbidden_reason = ""
            if isinstance(q_data, dict):
                forbidden_reason = str(q_data.get("forbidden_reason") or (q_data.get("quota") or {}).get("forbidden_reason") or "")
            print(f"[Watchdog Healer] Quota still forbidden or malformed for {target_email} ({forbidden_reason[:60]}). Retaining lock.", flush=True)
            return None

        # Stage 3: Proxy Activation (POST /toggle-proxy with enable=True)
        en_res = requests.post(toggle_url, headers=headers, json={"enable": True}, timeout=10)
        if en_res.status_code == 200:
            clear_account_healer_state(target_id)
            print(f"[Watchdog Healer] Successfully auto-healed and reloaded account {target_email} ({target_id})!", flush=True)
            notify_chatops(
                "TỰ ĐỘNG PHỤC HỒI TÀI KHOẢN (HEALTH PROBE PASSED)",
                f"✅ Tài khoản `{target_email}` đã tự động vượt qua Health Probe sau thời gian hạ nhiệt.\n"
                f"• **Trạng thái**: Đã kích hoạt lại thành công vào RAM Rotation Pool.\n"
                f"• **Thời gian phục hồi**: {datetime.datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
                actions=[],
                severity="INFO",
            )
            return target_email
        else:
            print(f"[Watchdog Healer] Toggle proxy failed with HTTP {en_res.status_code} for {target_email}.", flush=True)
            return None
    except Exception as e:
        print(f"[Watchdog Healer Error] Probe error for {target_email}: {e}", flush=True)
        return None


def check_quota_pool() -> None:
    """Monitors Antigravity Tools account pool health and detects checkpoints."""
    auth_key = GATEWAY_ADMIN_PASSWORD or GATEWAY_PROXY_KEY
    if not auth_key:
        return
    base_url = get_proxy_base_url()
    headers = {"Authorization": f"Bearer {auth_key}"}
    try:
        res = requests.get(f"{base_url}/api/accounts", headers=headers, timeout=5)
        if res.status_code != 200:
            return

        data = res.json()
        accounts = data.get("accounts", []) if isinstance(data, dict) else data
        total = len(accounts)
        if total == 0:
            return

        current_blocked: Dict[str, Dict[str, Any]] = {}
        active_count = 0

        for a in accounts:
            email = a.get("email", "unknown")
            is_blocked = is_account_blocked(a)
            if is_blocked:
                val_url = extract_validation_url(a)
                raw_reason = (
                    a.get("validation_blocked_reason")
                    or a.get("proxy_disabled_reason")
                    or a.get("disabled_reason")
                    or (a.get("quota") or {}).get("forbidden_reason")
                    or "Tài khoản bị ngắt kết nối tạm thời"
                )
                current_blocked[email] = {
                    "id": a.get("id"),
                    "reason": str(raw_reason),
                    "validation_url": val_url,
                }
            else:
                active_count += 1

        # Dọn dẹp trạng thái healer cho các tài khoản không còn blocked:
        blocked_ids = {str(a.get("id")) for a in accounts if is_account_blocked(a)}
        healer_ids = set(_healer_memory_first_seen.keys())
        r = _get_redis_client()
        if r:
            try:
                for k in r.scan_iter(match="watchdog:healer:first_seen:*", count=100):
                    k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                    healer_ids.add(k_str.replace("watchdog:healer:first_seen:", ""))
            except Exception as e:
                print(f"[Watchdog Healer State Warning] Redis scan error: {e}", flush=True)

        for acc_id in (healer_ids - blocked_ids):
            clear_account_healer_state(acc_id)

        now = time.time()
        failed_count = len(current_blocked)
        failed_ratio = (failed_count / total) if total > 0 else 0.0

        # Quorum Guard:
        # If failed_ratio >= 0.5 or active_count <= 2 (when total > 2), this is a mass/infrastructure failure
        # rather than individual account corruption. Dispatch CRITICAL warning instead of isolating individual accounts.
        if failed_count > 0 and (failed_ratio >= 0.5 or (total > 2 and active_count <= 2)):
            last_crit = getattr(check_quota_pool, "last_quorum_alert", 0.0)
            if now - last_crit >= 1800:
                check_quota_pool.last_quorum_alert = now
                title = "CẢNH BÁO NGUY CẤP: SỰ CỐ MẠNG / QUORUM GUARD KÍCH HOẠT"
                body = (
                    f"🚨 *Phát hiện sự cố hàng loạt trên Antigravity Pool ({failed_count}/{total} tài khoản bị lỗi, tỷ lệ lỗi {failed_ratio*100:.1f}%)!*\n\n"
                    f"• **Trạng thái Pool**: Chỉ còn `{active_count}/{total}` tài khoản khả dụng.\n"
                    f"• **Quorum Guard**: Đã tự động chặn cô lập tài khoản đơn lẻ để phòng chống Sập Dây Chuyền (Cascading Collapse).\n"
                    f"• **Chẩn đoán**: Sự cố có khả năng bắt nguồn từ mạng diện rộng, lỗi IP, hoặc máy chủ Google chặn kết nối tạm thời."
                )
                notify_chatops(title, body, actions=[], severity="CRITICAL")
            return

        # Quorum Condition satisfied: active_count > 2 and failed_ratio < 0.5
        # 1. Alert for newly blocked accounts (cooldown: 2 hours per account)
        for email, info in current_blocked.items():
            last_alert = known_blocked_accounts.get(email, 0.0)
            if now - last_alert >= 7200:
                known_blocked_accounts[email] = now
                val_url = info.get("validation_url")
                raw_reason = info.get("reason", "")
                acc_id = info.get("id")

                if "Verify your account" in raw_reason:
                    reason_desc = "Yêu cầu xác minh danh tính người dùng (VALIDATION_REQUIRED 403)"
                elif "quota fetch denied" in raw_reason:
                    reason_desc = "Không thể lấy hạn mức (Warmup 403 Forbidden)"
                elif "invalid_grant" in raw_reason:
                    reason_desc = "Phiên đăng nhập hết hạn (invalid_grant)"
                else:
                    reason_desc = raw_reason[:120]

                title = "CẢNH BÁO TÀI KHOẢN GOOGLE CẦN XÁC MINH"
                body = (
                    f"⚠️ *Tài khoản `{email}` tạm thời bị ngắt kết nối!*\n"
                    f"• **Lý do**: {reason_desc}\n"
                    f"• **Trạng thái Pool**: Còn `{active_count}/{total}` tài khoản khả dụng.\n"
                )
                if val_url:
                    body += (
                        f"\n🔗 **Link xác thực Google (1-Click):**\n"
                        f"[👉 Bấm vào đây để mở khóa tài khoản]({val_url})\n\n"
                        f"_Sau khi xác minh trên trình duyệt, hãy bấm nút Bật Lại bên dưới._"
                    )

                actions = []
                if acc_id:
                    actions.append({
                        "action_id": f"antigravity_reenable_{acc_id}",
                        "label": "🔄 Bật Lại (Health Probe)",
                        "command": "antigravity.account.reenable",
                        "params": {"account_id": str(acc_id)},
                        "callback_data": f"act:antigravity_reenable:{acc_id}",
                    })

                notify_chatops(title, body, actions=actions, severity="WARNING")

        # 2. Alert for newly recovered accounts
        for email in list(known_blocked_accounts.keys()):
            if email not in current_blocked:
                del known_blocked_accounts[email]
                title = "TÀI KHOẢN GOOGLE ĐÃ PHỤC HỒI"
                body = (
                    f"✅ Tài khoản `{email}` đã được kích hoạt lại thành công!\n"
                    f"• Hiện có `{active_count}/{total}` tài khoản sẵn sàng phục vụ."
                )
                notify_chatops(title, body, actions=[], severity="INFO")

        # 3. Automated Auto-Healing Loop (Phase 2)
        # Quorum is guaranteed healthy here (mass failure returned early above)
        if current_blocked:
            auto_heal_single_candidate(accounts, base_url, headers)
    except requests.RequestException as e:
        print(f"Error checking quota pool: {e}", flush=True)


def get_hardware_metrics() -> str:
    """Collects host RAM, NVMe disk, and SoC thermal metrics."""
    parts = []
    # 1. RAM & Swap via /proc/meminfo
    try:
        with open("/proc/meminfo") as f:
            mem_data = {}
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    mem_data[k.strip()] = v.strip()
            total_gb = int(mem_data["MemTotal"].split()[0]) / 1024 / 1024
            avail_gb = int(mem_data["MemAvailable"].split()[0]) / 1024 / 1024
            used_gb = total_gb - avail_gb
            parts.append(f"RAM: {used_gb:.0f}G/{total_gb:.0f}G ({avail_gb:.0f}G trống)")

            swap_tot_kb = int(mem_data.get("SwapTotal", "0").split()[0])
            swap_free_kb = int(mem_data.get("SwapFree", "0").split()[0])
            if swap_tot_kb > 0:
                swap_tot_gb = swap_tot_kb / 1024 / 1024
                swap_used_gb = (swap_tot_kb - swap_free_kb) / 1024 / 1024
                swap_pct = (swap_used_gb / swap_tot_gb) * 100
                parts.append(f"Swap: {swap_used_gb:.1f}G/{swap_tot_gb:.0f}G ({swap_pct:.0f}%)")
    except Exception:
        pass

    # 2. Disk via shutil.disk_usage
    try:
        total, used, _ = shutil.disk_usage("/")
        tot_tb = total / (1024 ** 4)
        used_tb = used / (1024 ** 4)
        pct = (used / total) * 100
        parts.append(f"NVMe: {used_tb:.1f}T/{tot_tb:.1f}T ({pct:.0f}%)")
    except Exception:
        pass

    # 3. SoC Thermal
    try:
        temps = []
        for i in range(5):
            p = f"/sys/class/thermal/thermal_zone{i}/temp"
            if os.path.exists(p):
                with open(p) as f:
                    val = int(f.read().strip()) / 1000.0
                    if 30 <= val <= 100:
                        temps.append(val)
        if temps:
            avg_temp = sum(temps) / len(temps)
            parts.append(f"SoC Temp: {avg_temp:.0f}°C")
    except Exception:
        pass

    return "• " + " | ".join(parts) if parts else "• Phần cứng: Bình thường"


def get_top_models(base_url: str, headers: Dict[str, str]) -> str:
    """Fetches top 2 consumed models from Antigravity Tools API."""
    try:
        res = requests.get(f"{base_url}/api/stats/token/by-model", headers=headers, timeout=5)
        if res.status_code == 200:
            models = res.json()
            if isinstance(models, list) and models:
                sorted_models = sorted(models, key=lambda m: m.get("total_tokens", 0), reverse=True)
                top_items = []
                for m in sorted_models[:2]:
                    name = m.get("model", "unknown")
                    tokens = m.get("total_tokens", 0)
                    tok_str = f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)
                    top_items.append(f"{name} ({tok_str})")
                if top_items:
                    return "• Top Models: " + ", ".join(top_items)
    except Exception:
        pass
    return "• Top Models: Chưa có dữ liệu"


def get_gateway_telemetry_digest() -> str:
    """Retrieve 24h AI Gateway usage metrics from LiteLLM PostgreSQL."""
    try:
        raw_output = ""
        top_output = ""
        try:
            import docker
            client = docker.from_env()
            container = client.containers.get("litellm-postgres")
            cmd = (
                'psql -U litellm -d litellm --csv -c "'
                'SELECT COUNT(*) as reqs, COALESCE(SUM(total_tokens), 0) as tokens, '
                'ROUND(AVG(EXTRACT(EPOCH FROM (\\"endTime\\" - \\"startTime\\")))::numeric, 2) as avg_lat '
                'FROM \\"LiteLLM_SpendLogs\\" '
                'WHERE \\"startTime\\" >= NOW() - INTERVAL \'24 hours\';"'
            )
            res = container.exec_run(cmd)
            if res.exit_code == 0:
                raw_output = res.output.decode("utf-8")
            cmd_top = (
                'psql -U litellm -d litellm --csv -c "'
                'SELECT regexp_replace(model, \'^(openai|gemini)/\', \'\') as clean_model, '
                'COUNT(*) as cnt, COALESCE(SUM(total_tokens), 0) as tok '
                'FROM \\"LiteLLM_SpendLogs\\" '
                'WHERE \\"startTime\\" >= NOW() - INTERVAL \'24 hours\' '
                'GROUP BY clean_model ORDER BY cnt DESC LIMIT 3;"'
            )
            res_top = container.exec_run(cmd_top)
            if res_top.exit_code == 0:
                top_output = res_top.output.decode("utf-8")
        except Exception:
            import subprocess
            cmd = [
                "docker", "exec", "-i", "litellm-postgres",
                "psql", "-U", "litellm", "-d", "litellm", "--csv", "-c",
                (
                    'SELECT COUNT(*) as reqs, COALESCE(SUM(total_tokens), 0) as tokens, '
                    'ROUND(AVG(EXTRACT(EPOCH FROM ("endTime" - "startTime")))::numeric, 2) as avg_lat '
                    'FROM "LiteLLM_SpendLogs" WHERE "startTime" >= NOW() - INTERVAL \'24 hours\';'
                )
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                raw_output = res.stdout
            cmd_top = [
                "docker", "exec", "-i", "litellm-postgres",
                "psql", "-U", "litellm", "-d", "litellm", "--csv", "-c",
                (
                    "SELECT regexp_replace(model, '^(openai|gemini)/', '') as clean_model, COUNT(*) as cnt, "
                    'COALESCE(SUM(total_tokens), 0) as tok FROM "LiteLLM_SpendLogs" '
                    "WHERE \"startTime\" >= NOW() - INTERVAL '24 hours' GROUP BY clean_model ORDER BY cnt DESC LIMIT 3;"
                )
            ]
            res_top = subprocess.run(cmd_top, capture_output=True, text=True)
            if res_top.returncode == 0:
                top_output = res_top.stdout

        lines = [line.strip() for line in raw_output.strip().splitlines() if line.strip()]
        if len(lines) >= 2:
            parts = lines[1].split(",")
            reqs = int(parts[0]) if parts[0] else 0
            tokens = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            avg_lat = parts[2] if len(parts) > 2 else "0.0"
            tok_str = f"{tokens / 1000000:.2f}M" if tokens >= 1000000 else (f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens))

            top_items = []
            for t_line in [row.strip() for row in top_output.strip().splitlines() if row.strip()][1:]:
                t_parts = t_line.split(",")
                if len(t_parts) >= 3:
                    m_name = t_parts[0].replace("openai/", "").replace("gemini/", "")  # ccba:allow-raw-model
                    m_tok = int(t_parts[2]) if t_parts[2] else 0
                    m_tok_str = f"{m_tok / 1000000:.1f}M" if m_tok >= 1000000 else (f"{m_tok / 1000:.1f}k" if m_tok >= 1000 else str(m_tok))
                    top_items.append(f"{m_name} ({t_parts[1]} reqs, {m_tok_str})")
            top_str = " | ".join(top_items) if top_items else "Chưa có dữ liệu"

            return (
                f"• Tổng Gateway (24h): {reqs:,} requests | Tokens: {tok_str} | Đ/trễ TB: {avg_lat}s\n"
                f"• Top Models Gateway: {top_str}"
            )
    except Exception:
        pass
    return "• AI Gateway: Chưa có dữ liệu"


def build_daily_digest_message(date_str: str) -> str:
    """Constructs the daily summary report markdown."""
    base_url = get_proxy_base_url()
    auth_key = GATEWAY_ADMIN_PASSWORD or GATEWAY_PROXY_KEY
    headers = {"Authorization": f"Bearer {auth_key}"} if auth_key else {}

    # 1. Hardware metrics
    hw_line = get_hardware_metrics()

    # 2. Token stats
    stats_lines = "• Không lấy được số liệu thống kê."
    try:
        res = requests.get(f"{base_url}/api/stats/token/summary", headers=headers, timeout=5)
        if res.status_code == 200:
            s = res.json()
            tot_req = s.get("total_requests", 0)
            tot_tok = s.get("total_tokens", 0)
            in_tok = s.get("total_input_tokens", 0)
            out_tok = s.get("total_output_tokens", 0)
            cached = s.get("total_cached_tokens", 0)
            cache_pct = (cached / in_tok * 100) if in_tok > 0 else 0.0
            in_str = f"{in_tok / 1000:.1f}k" if in_tok >= 1000 else str(in_tok)
            out_str = f"{out_tok / 1000:.1f}k" if out_tok >= 1000 else str(out_tok)
            stats_lines = (
                f"• Tổng requests: {tot_req:,} requests | Tổng tokens: {tot_tok:,}\n"
                f"• Input: {in_str} | Output: {out_str} | Cache Hit: {cache_pct:.1f}%"
            )
    except Exception as e:
        stats_lines = f"• Lỗi đọc thống kê: {e}"

    # 3. Top models
    top_models_line = get_top_models(base_url, headers)

    # 4. Gateway Telemetry (PostgreSQL)
    gateway_line = get_gateway_telemetry_digest()

    # 5. Account pool
    acc_line = "• Quota Pool: Đang kiểm tra..."
    try:
        res = requests.get(f"{base_url}/api/accounts", headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            accounts = data.get("accounts", []) if isinstance(data, dict) else data
            active = sum(
                1 for a in accounts
                if not is_account_blocked(a)
            )
            blocked = len(accounts) - active
            if blocked > 0:
                acc_line = f"• Quota Pool: `{active}/{len(accounts)}` accounts khả dụng ({blocked} tạm ngắt)"
            else:
                acc_line = f"• Quota Pool: `{active}/{len(accounts)}` accounts khả dụng (100% OK)"
    except Exception as e:
        acc_line = f"• Quota Pool: Lỗi đọc dữ liệu ({e})"

    return (
        f"📊 **[SPARK-AI] BÁO CÁO HOẠT ĐỘNG NGÀY {date_str}** 📊\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ **Dịch vụ & Phần cứng (DGX Spark GB10):**\n"
        f"• AI Gateway (`:8090`): Online | Antigravity (`:8045`): Online (CacheFirst)\n"
        f"• vLLM (`:8004`): Online\n"
        f"{hw_line}\n\n"
        f"📈 **Sản lượng Token & Requests:**\n"
        f"**[Cloud Proxy :8045]**\n"
        f"{stats_lines}\n"
        f"{top_models_line}\n"
        f"**[AI Gateway :8090 - Toàn Hệ Thống]**\n"
        f"{gateway_line}\n\n"
        f"👥 **Tài khoản & Quota:**\n"
        f"{acc_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


VN_TZ = datetime.timezone(datetime.timedelta(hours=7))


def check_and_send_daily_digest() -> None:
    """Checks if current time in VN (ICT) is within 08:00-08:59 and sends daily digest once."""
    global last_digest_date
    now = datetime.datetime.now(VN_TZ)
    today_str = now.strftime("%Y-%m-%d")

    if now.hour == 8 and last_digest_date != today_str:
        msg = build_daily_digest_message(today_str)
        if send_telegram_raw(msg):
            last_digest_date = today_str
            print(f"Sent daily digest for {today_str} (VN Time: {now.strftime('%H:%M:%S')})", flush=True)


# Upstream Release Check Tracking
LAST_UPSTREAM_CHECK: float = 0.0
UPSTREAM_CHECK_INTERVAL: float = 6 * 3600  # Scan every 6 hours


def check_openwebui_updates() -> None:
    """Checks for new Open WebUI releases safely without quota burnout."""
    global LAST_UPSTREAM_CHECK
    now = time.time()
    if now - LAST_UPSTREAM_CHECK < UPSTREAM_CHECK_INTERVAL:
        return
    LAST_UPSTREAM_CHECK = now

    try:
        cur_res = requests.get("http://open-webui:8080/api/version", timeout=5)
        if cur_res.status_code != 200:
            return
        cur_ver = cur_res.json().get("version", "unknown").lstrip("v")

        gh_res = requests.get(
            "https://api.github.com/repos/open-webui/open-webui/releases/latest",
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "DGX-Spark-Watchdog"},
            timeout=10,
        )
        if gh_res.status_code == 200:
            rel = gh_res.json()
            latest_tag = rel.get("tag_name", "").lstrip("v")
            html_url = rel.get("html_url", "https://github.com/open-webui/open-webui/releases")
            pub_date = rel.get("published_at", "")[:10]

            if latest_tag and latest_tag != cur_ver:
                title = f"CÓ BẢN CẬP NHẬT MỚI: Open WebUI v{latest_tag}"
                body = (
                    f"• Phiên bản đang chạy: `v{cur_ver}`\n"
                    f"• Phiên bản mới nhất: `v{latest_tag}` ({pub_date})\n"
                    f"• Xem chi tiết: [GitHub Release Notes]({html_url})\n\n"
                    f"💡 *Nâng cấp an toàn (Zero Data Loss & Auto-Rollback)*"
                )
                actions = [
                    {
                        "action_id": f"upg_{latest_tag}",
                        "label": f"🚀 Nâng Cấp v{latest_tag} Ngay",
                        "command": "system.openwebui.upgrade",
                        "params": {"target_version": f"v{latest_tag}"},
                        "ttl_seconds": 86400,
                    }
                ]
                notify_chatops(title, body, actions=actions, severity="WARNING")
    except Exception as e:
        print(f"Update check error: {e}", flush=True)


def check_swap_pressure() -> None:
    """Monitors memory pressure and triggers Backpressure only when RAM is actually low."""
    try:
        with open("/proc/meminfo") as f:
            mem_data = {}
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    mem_data[k.strip()] = v.strip()
        swap_tot_kb = int(mem_data.get("SwapTotal", "0").split()[0])
        swap_free_kb = int(mem_data.get("SwapFree", "0").split()[0])
        avail_kb = int(mem_data.get("MemAvailable", "0").split()[0])
        avail_gb = avail_kb / 1024 / 1024

        swap_used_gb = 0.0
        swap_tot_gb = swap_tot_kb / 1024 / 1024 if swap_tot_kb > 0 else 0.0
        swap_pct = 0.0
        if swap_tot_kb > 0:
            swap_used_kb = swap_tot_kb - swap_free_kb
            swap_pct = (swap_used_kb / swap_tot_kb) * 100
            swap_used_gb = swap_used_kb / 1024 / 1024

        # Real pressure occurs when RAM is critically low (< 6GB) OR both Swap is high (>= 35%) and RAM is constrained (< 10GB).
        # Idle cold memory swapped out to disk with > 10GB available RAM is healthy on Linux unified memory.
        under_pressure = (avail_gb < 6.0 and avail_gb > 0) or (swap_pct >= 35.0 and avail_gb < 10.0)

        redis_url = os.getenv("REDIS_URL", "redis://litellm-redis:6379/1")
        if under_pressure:
            try:
                import redis
                r = redis.Redis.from_url(redis_url, socket_timeout=2)
                r.set("rag:ingestion:paused", "1", ex=300)
                print(f"[BACKPRESSURE] Activated rag:ingestion:paused (TTL 300s). Avail RAM: {avail_gb:.1f}GB, Swap: {swap_used_gb:.1f}GB", flush=True)
            except Exception as rx:
                print(f"Could not set backpressure redis flag: {rx}", flush=True)

            current_time = time.time()
            last_alert = getattr(check_swap_pressure, "last_alert_time", 0)
            if current_time - last_alert >= 900:  # 15 minutes cooldown
                check_swap_pressure.last_alert_time = current_time
                title = f"CẢNH BÁO ÁP LỰC BỘ NHỚ: RAM {avail_gb:.1f}G, SWAP {swap_used_gb:.1f}G/{swap_tot_gb:.0f}G ({swap_pct:.0f}%)"
                body = (
                    f"⚠️ *DGX Spark đang chịu áp lực bộ nhớ cao!*\n"
                    f"• RAM khả dụng: `{avail_gb:.1f} GiB` (Ngưỡng an toàn >= 10.0 GiB)\n"
                    f"• Swap tiêu thụ: `{swap_used_gb:.1f} GiB / {swap_tot_gb:.0f} GiB` (`{swap_pct:.0f}%`)\n"
                    f"🛑 *Cơ chế Backpressure đã tự động tạm hoãn nhận tài liệu mới vào queue trong 5 phút.*\n"
                    f"💡 *Gợi ý: Dùng lệnh `/memory` trên Telegram để kiểm tra tiến trình.*"
                )
                actions = [
                    {
                        "action_id": "inspect_memory",
                        "label": "🧠 Xem Chi Tiết Bộ Nhớ",
                        "command": "system.memory",
                        "params": {},
                    }
                ]
                notify_chatops(title, body, actions=actions, severity="WARNING")
        else:
            # If system is healthy, clear any existing paused flag so ingestion resumes immediately
            try:
                import redis
                r = redis.Redis.from_url(redis_url, socket_timeout=2)
                if r.exists("rag:ingestion:paused"):
                    r.delete("rag:ingestion:paused")
                    print(f"[BACKPRESSURE] System healthy (RAM: {avail_gb:.1f}GB, Swap: {swap_used_gb:.1f}GB). Relieved rag:ingestion:paused.", flush=True)
            except Exception:
                pass
    except Exception as e:
        print(f"Error checking swap pressure: {e}", flush=True)


def run_watchdog_cycle() -> None:
    """Executes a single check cycle for all monitored components."""
    check_docker_containers()
    check_vllm_deadlock()
    check_ai_gateway()
    check_antigravity_tools()
    check_quota_pool()
    check_swap_pressure()
    check_and_send_daily_digest()
    check_openwebui_updates()


def main() -> None:
    """Entrypoint for the smart watchdog service loop."""
    print("Smart Watchdog is starting with Antigravity & Daily Digest support...", flush=True)
    while True:
        try:
            run_watchdog_cycle()
        except Exception as e:
            print(f"Watchdog cycle error: {e}", flush=True)
        # Sleep for 10 minutes (600s) between cycles
        time.sleep(600)


if __name__ == "__main__":
    main()
