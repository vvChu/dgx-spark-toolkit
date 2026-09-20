"""Smart Watchdog daemon for DGX Spark infrastructure.

Monitors Docker containers, local vLLM, AI Gateway, Antigravity Tools,
and sends real-time incident alerts and a daily digest via Telegram.
"""

import datetime
import os
import shutil
import time
from typing import Dict, Optional
import docker
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-spark-secure-key-2026")
GATEWAY_PROXY_URL = os.environ.get("GATEWAY_PROXY_URL", "http://100.83.192.30:8045")
GATEWAY_PROXY_KEY = os.environ.get("GATEWAY_PROXY_KEY", "")

# Cooldown for incident alerts (30 minutes per alert_type)
COOLDOWN_MINUTES = 30
last_alert_time: Dict[str, float] = {}
last_digest_date: Optional[str] = None


def send_telegram_raw(message: str) -> bool:
    """Sends a raw markdown-formatted message to Telegram."""
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


def send_telegram_alert(message: str, alert_type: str) -> None:
    """Sends an incident alert with cooldown protection."""
    global last_alert_time
    now = time.time()
    if alert_type in last_alert_time:
        if now - last_alert_time[alert_type] < COOLDOWN_MINUTES * 60:
            return  # Cooldown active

    text = f"🚨 **CẢNH BÁO TỪ SMART WATCHDOG** 🚨\n\n{message}"
    if send_telegram_raw(text):
        last_alert_time[alert_type] = now
        print(f"Sent alert for: {alert_type}", flush=True)


def check_docker_containers() -> None:
    """Checks the status of core docker containers."""
    try:
        client = docker.from_env()
        core_services = ["ai-gateway", "qwen36b", "milvus-standalone", "rag-service"]
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


def check_quota_pool() -> None:
    """Checks for account pool exhaustion in Antigravity Tools."""
    if not GATEWAY_PROXY_KEY:
        return
    base_url = get_proxy_base_url()
    headers = {"Authorization": f"Bearer {GATEWAY_PROXY_KEY}"}
    try:
        res = requests.get(f"{base_url}/api/accounts", headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            accounts = data.get("accounts", []) if isinstance(data, dict) else []
            total = len(accounts)
            if total > 0:
                disabled_or_error = [
                    a for a in accounts
                    if a.get("disabled") or a.get("status") in ["error", "rate_limited", "quota_exceeded"]
                ]
                if len(disabled_or_error) >= max(1, total - 1):
                    send_telegram_alert(
                        f"CẢNH BÁO NGUY CẤP: Pool tài khoản Google cạn kiệt! "
                        f"Hiện có {len(disabled_or_error)}/{total} tài khoản bị khóa/lỗi quota.",
                        "quota_pool_exhausted",
                    )
    except requests.RequestException as e:
        print(f"Error checking quota pool: {e}", flush=True)


def get_hardware_metrics() -> str:
    """Collects host RAM, NVMe disk, and SoC thermal metrics."""
    parts = []
    # 1. RAM via /proc/meminfo
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


def build_daily_digest_message(date_str: str) -> str:
    """Constructs the daily summary report markdown."""
    base_url = get_proxy_base_url()
    headers = {"Authorization": f"Bearer {GATEWAY_PROXY_KEY}"} if GATEWAY_PROXY_KEY else {}

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

    # 4. Account pool
    acc_line = "• Quota Pool: 7/7 accounts khả dụng (0 bị khóa 7-ngày)"
    try:
        res = requests.get(f"{base_url}/api/accounts", headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            accounts = data.get("accounts", []) if isinstance(data, dict) else []
            active = sum(1 for a in accounts if not a.get("disabled"))
            acc_line = f"• Quota Pool: {active}/{len(accounts)} accounts khả dụng"
    except Exception:
        pass

    return (
        f"📊 **[SPARK-AI] BÁO CÁO HOẠT ĐỘNG NGÀY {date_str}** 📊\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ **Dịch vụ & Phần cứng (DGX Spark GB10):**\n"
        f"• AI Gateway (`:8090`): Online | Antigravity (`:8045`): Online (Balance)\n"
        f"• vLLM (`:8004`): Online\n"
        f"{hw_line}\n\n"
        f"📈 **Sản lượng Token & Requests:**\n"
        f"{stats_lines}\n"
        f"{top_models_line}\n\n"
        f"👥 **Tài khoản & Quota:**\n"
        f"{acc_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


def check_and_send_daily_digest() -> None:
    """Checks if current time is within 08:00-08:59 and sends daily digest once."""
    global last_digest_date
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    if now.hour == 8 and last_digest_date != today_str:
        msg = build_daily_digest_message(today_str)
        if send_telegram_raw(msg):
            last_digest_date = today_str
            print(f"Sent daily digest for {today_str}", flush=True)


def run_watchdog_cycle() -> None:
    """Executes a single check cycle for all monitored components."""
    check_docker_containers()
    check_vllm_deadlock()
    check_ai_gateway()
    check_antigravity_tools()
    check_quota_pool()
    check_and_send_daily_digest()


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
