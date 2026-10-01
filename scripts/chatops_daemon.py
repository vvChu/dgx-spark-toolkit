#!/usr/bin/env python3
"""DGX-ChatOps Universal Gateway.

Two-way interactive ChatOps daemon for NVIDIA DGX Spark infrastructure.
Features:
- Long Polling Telegram Bot (Zero ingress ports exposed to the Internet)
- Interactive Dashboard Menu with In-Place Message Updates
- Internal REST API (:8095) for Docker container alerts with Action Buttons
- Two-Tier Output Delivery (Summary + Attached .log file for long outputs)
- Chained SHA-256 Audit Trail
- Emergency Shell execution (/exec [PIN] [cmd]) with Brute-Force Lockout & Two-Phase Confirmation
- Unified Memory parser for NVIDIA Blackwell GB10
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import sys
import time
import tomllib
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response
import httpx
import uvicorn
import yaml

# --- 1. CONFIGURATION & PATH SETUP ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
ADMIN_USER_ID = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID.isdigit() else 0

CHATOPS_PORT = int(os.environ.get("CHATOPS_PORT", "8095"))
CHATOPS_INTERNAL_SECRET = os.environ.get("CHATOPS_INTERNAL_SECRET", "").strip()
CHATOPS_EMERGENCY_PIN = os.environ.get("CHATOPS_EMERGENCY_PIN", "").strip()

if not CHATOPS_INTERNAL_SECRET:
    print("[Security Error] CHATOPS_INTERNAL_SECRET is not configured in .env! Internal notify endpoint will reject all requests.", flush=True)

if not CHATOPS_EMERGENCY_PIN or len(CHATOPS_EMERGENCY_PIN) < 6:
    print("[Security Warning] CHATOPS_EMERGENCY_PIN is not configured or < 6 digits! Emergency /exec is disabled.", flush=True)

LOG_DIR = PROJECT_ROOT / "logs" / "chatops"
LOG_DIR.mkdir(parents=True, exist_ok=True)

STATE_DIR = Path.home() / ".local" / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

LOCK_FILE = STATE_DIR / "dgx_chatops.lock"
LOCKOUT_FILE = STATE_DIR / "chatops_lockout.json"
AUDIT_FILE = LOG_DIR / "audit.jsonl"
COMMANDS_FILE = PROJECT_ROOT / "scripts" / "chatops_commands.yaml"
GROK_CONFIG_PATH = Path.home() / ".grok" / "config.toml"

# --- Externalized Microservices & Database Endpoints ---
RAG_SERVICE_URL = os.environ.get("RAG_SERVICE_URL", "http://127.0.0.1:8005").rstrip("/")
OPENWEBUI_URL = os.environ.get("OPENWEBUI_URL", "http://127.0.0.1:3001").rstrip("/")
RAG_TARGET_DOCS = int(os.environ.get("RAG_TARGET_DOCS", "8870"))

LITELLM_PG_CONTAINER = os.environ.get("LITELLM_PG_CONTAINER", "litellm-postgres")
LITELLM_PG_USER = os.environ.get("LITELLM_PG_USER", "litellm")
LITELLM_PG_DATABASE = os.environ.get("LITELLM_PG_DATABASE", "litellm")

# Core containers monitored by /status (aligned with restart whitelist)
CORE_CONTAINER_KEYWORDS = [
    "open-webui",
    "ai-gateway",
    "qwen36b",
    "smart-watchdog",
    "cloudflared",
    "rag-service",
    "milvus",
    "neo4j",
    "dgx-spark-ocr-worker",
    "rag-frontend",
    "whisper-local",
]

# ccba:allow-raw-model
GROK_AVAILABLE_MODELS = [
    ("qwen-local", "🟢 Qwen 35B Local (GPU)"),
    ("gemini-38-flash", "⚡ Gemini 3.8 Flash"),
    ("claude-sonnet-4-6", "🧠 Claude Sonnet 4.6"),
    ("claude-opus-4-6", "🚀 Claude Opus 4.6"),
    ("grok-4.7", "⭐ Grok 4.7 (xAI)"),
    ("grok-4.7-build-fast", "🏎️ Grok 4.7 Fast"),
    ("grok-4.6", "🌪️ Grok 4.6 (xAI)"),
    ("grok-4.5", "📦 Grok 4.5 (xAI)"),
]

GROK_EFFORT_LEVELS = [
    ("low", "🟢 Low (Tiết kiệm)"),
    ("medium", "🟡 Medium (Cân bằng)"),
    ("high", "🟠 High (Suy luận sâu)"),
    ("xhigh", "🔴 xHigh (Tối đa)"),
]

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Allowed internal networks for REST endpoint
ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),  # ccba:allow-raw-ip
]

# Blacklisted dangerous shell patterns for /exec
SHELL_BLACKLIST = [
    r"\brm\s+-rf\s+/\b",
    r"\brm\s+-rf\s+~\b",
    r"\bmkfs\b",
    r"\bdd\s+if=.*of=/dev/(sd|nvme|loop)",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"\bshutdown\b",
    r"\bpoweroff\b",
    r"\binit\s+0\b",
]

# Help Text single source of truth (P1-03)
HELP_TEXT: str = (
    "❓ *HƯỚNG DẪN SỬ DỤNG DGX-CHATOPS*\n\n"
    "• `/menu` hoặc `/start`: Bật bảng điều khiển cảm ứng.\n"
    "• `/status`: Kiểm tra nhanh phần cứng & containers.\n"
    "• `/memory`: Chi tiết RAM, Swap và Top 5 tiến trình ngốn bộ nhớ.\n"
    "• `/stats`: Thống kê sản lượng Tokens, Requests (Dual-Gateway).\n"
    "• `/gpu`: Xem nhiệt độ, VRAM GPU Blackwell GB10.\n"
    "• `/autotuner`: Kiểm tra tiến độ Nightly Auto-Tuner CCBA.\n"
    "• `/rag_state`: Xem tiến độ hàng đợi RAG Ingestion.\n"
    "• `/antigravity`: Kiểm tra hồ bơi tài khoản Antigravity.\n"
    "• `/reenable_account <id>`: Kích hoạt lại tài khoản Antigravity (Health Probe).\n"
    "• `/deps`: Rà soát độ trễ phiên bản và lỗ hổng bảo mật phụ thuộc.\n"
    "• `/upgrade_deps [patch|minor]`: Nâng cấp phụ thuộc 1-Click kèm Hard Completion Lock.\n"
    "• `/grok`: Bật bảng điều khiển cảm ứng đổi model cho Grok Build CLI.\n"
    "• `/grok_effort [low|medium|high]`: Chuyển mức suy luận Grok CLI.\n"
    "• `/set_grok_model <model>`: Chuyển đổi nhanh model Grok CLI.\n"
    "• `/restart <service>`: Khởi động lại container.\n"
    "• `/upgrade_owu`: Nâng cấp Open WebUI.\n"
    "• `/boost <skill>`: Tăng cường suy luận sâu cho kỹ năng bị kẹt (ADR-0052).\n"
    "• `/exec <PIN> <command>`: Thực thi lệnh khẩn cấp (có 2-step confirmation).\n"
)


def escape_md(text: str) -> str:
    """Escapes Telegram Markdown (v1) special formatting characters in raw dynamic text."""
    if not text:
        return ""
    return re.sub(r"([_*`\[])", r"\\\1", str(text))


async def run_probe_command(
    cmd: List[str],
    timeout: float = 10.0,
    cwd: Optional[Union[str, Path]] = None,
) -> Tuple[int, bytes, bytes]:
    """Runs an OS probe command with timeout and process kill escalation.

    Returns:
        Tuple of (returncode, stdout_bytes, stderr_bytes). If timed out or errored,
        returncode is -1 and stderr contains the error message.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except Exception as e:
        return -1, b"", str(e).encode()

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, stdout or b"", stderr or b""
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        return -1, b"", b"Probe command timed out"
    except asyncio.CancelledError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise


# --- 2. IN-MEMORY STATE & MUTEXES ---
action_cache: Dict[str, Dict[str, Any]] = {}
heavy_op_lock = asyncio.Lock()
service_locks: Dict[str, asyncio.Lock] = {}
http_client: Optional[httpx.AsyncClient] = None
client_loop: Optional[asyncio.AbstractEventLoop] = None


def load_last_audit_hash() -> str:
    """Restores the last SHA-256 hash from audit.jsonl to maintain cryptographic chain continuity across restarts."""
    if not AUDIT_FILE.exists():
        return "0" * 64
    try:
        with open(AUDIT_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    h = record.get("record_hash")
                    if h and isinstance(h, str) and len(h) == 64:
                        return h
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"[Audit Warning] Failed to restore audit hash chain from {AUDIT_FILE}: {e}", flush=True)
    return "0" * 64


last_audit_hash: str = load_last_audit_hash()


def get_service_lock(service_name: str) -> asyncio.Lock:
    """Returns or creates a per-service lock."""
    if service_name not in service_locks:
        service_locks[service_name] = asyncio.Lock()
    return service_locks[service_name]


def is_kernel_runner_locked(lock_path: str = "/tmp/ccba_nightly_runner.lock") -> bool:
    """Checks whether the CCBA Nightly Auto-Tuner file lock is held."""
    p = Path(lock_path)
    if not p.exists():
        return False
    try:
        with open(p, "r") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return False
            except (BlockingIOError, OSError):
                return True
    except Exception:
        return False


def get_http_client() -> httpx.AsyncClient:
    """Returns or initializes the persistent httpx client with connection pooling and loop safety."""
    global http_client, client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if http_client is None or http_client.is_closed or (current_loop is not None and client_loop != current_loop):
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(45.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0),
        )
        client_loop = current_loop
    return http_client


# --- 3. AUDIT LOGGER (CHAINED SHA-256) ---
def append_audit_log(
    trigger_type: str,
    command: str,
    params: Dict[str, Any],
    user_id: int,
    status: str,
    duration_ms: int,
    exit_code: int,
    details: str = "",
) -> None:
    """Appends an entry to audit.jsonl with cryptographic chaining."""
    global last_audit_hash
    ts = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp": ts,
        "user_id": user_id,
        "trigger_type": trigger_type,
        "command": command,
        "params": params,
        "status": status,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "details": details[:300],
        "prev_hash": last_audit_hash,
    }
    encoded = json.dumps(record, sort_keys=True).encode("utf-8")
    record_hash = hashlib.sha256(encoded).hexdigest()
    record["record_hash"] = record_hash
    last_audit_hash = record_hash

    try:
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Audit Error] Failed to write log: {e}", flush=True)


# --- 4. TELEGRAM API UTILITIES ---
async def telegram_request(method: str, payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Makes an async POST request to Telegram Bot API with persistent client."""
    url = f"{TELEGRAM_API_BASE}/{method}"
    try:
        client = get_http_client()
        res = await client.post(url, json=payload or {})
        data = res.json()
        if not data.get("ok"):
            print(f"[Telegram Error] {method}: {data.get('description')}", flush=True)
        return data
    except Exception as e:
        print(f"[Telegram Net Error] {method}: {e}", flush=True)
        return None


async def send_telegram_msg(
    chat_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = "Markdown",
) -> Optional[int]:
    """Sends a text message to Telegram, returning message_id on success."""
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode

    data = await telegram_request("sendMessage", payload)
    if not data or not data.get("ok"):
        # Fallback to plain text if Markdown/HTML parsing fails
        if parse_mode:
            payload.pop("parse_mode", None)
            data = await telegram_request("sendMessage", payload)
    if data and data.get("ok"):
        return data["result"]["message_id"]
    return None


async def edit_telegram_msg(
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = "Markdown",
) -> bool:
    """Edits an existing message in-place."""
    payload: Dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode

    data = await telegram_request("editMessageText", payload)
    if not data or not data.get("ok"):
        if parse_mode:
            payload.pop("parse_mode", None)
            data = await telegram_request("editMessageText", payload)
    return bool(data and data.get("ok"))


async def answer_callback(callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> None:
    """Dismisses Telegram spinner for a callback query."""
    payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    await telegram_request("answerCallbackQuery", payload)


async def send_telegram_document(chat_id: int, file_path: Path, caption: str = "") -> bool:
    """Sends a document file (.log) to Telegram with persistent client."""
    url = f"{TELEGRAM_API_BASE}/sendDocument"
    try:
        client = get_http_client()
        with open(file_path, "rb") as f:
            files = {"document": (file_path.name, f, "text/plain")}
            data = {"chat_id": str(chat_id), "caption": caption[:1000]}
            res = await client.post(url, data=data, files=files, timeout=60.0)
            return res.status_code == 200
    except Exception as e:
        print(f"[Document Send Error] {e}", flush=True)
        return False


async def delete_telegram_msg(chat_id: int, message_id: int) -> None:
    """Deletes a message from Telegram chat history."""
    await telegram_request("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


# --- 5. SYSTEM PROBING & COMMAND HANDLERS ---
async def probe_hardware_and_containers() -> str:
    """Probes CPU, Unified Memory, NVMe and active containers."""
    lines = ["🖥️ *BÁO CÁO HỆ THỐNG DGX SPARK* 🖥️\n"]

    # 1. RAM / Unified Memory
    try:
        with open("/proc/meminfo", "r") as f:
            mem = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    mem[parts[0].strip()] = parts[1].strip()
        total_gb = int(mem.get("MemTotal", "0").split()[0]) / 1024 / 1024
        avail_gb = int(mem.get("MemAvailable", "0").split()[0]) / 1024 / 1024
        used_gb = total_gb - avail_gb
        lines.append(f"• *RAM/Unified:* `{used_gb:.1f}G/{total_gb:.1f}G` (Trống {avail_gb:.1f}G)")

        swap_tot_kb = int(mem.get("SwapTotal", "0").split()[0])
        swap_free_kb = int(mem.get("SwapFree", "0").split()[0])
        if swap_tot_kb > 0:
            swap_tot_gb = swap_tot_kb / 1024 / 1024
            swap_used_gb = (swap_tot_kb - swap_free_kb) / 1024 / 1024
            swap_pct = (swap_used_gb / swap_tot_gb) * 100
            lines.append(f"• *Swap NVMe:* `{swap_used_gb:.1f}G/{swap_tot_gb:.0f}G` ({swap_pct:.0f}% dùng)")
    except Exception:
        pass

    # 2. Disk
    try:
        total, used, _ = shutil.disk_usage("/")
        tot_tb = total / (1024**4)
        used_tb = used / (1024**4)
        pct = (used / total) * 100
        lines.append(f"• *NVMe Storage:* `{used_tb:.1f}T/{tot_tb:.1f}T` ({pct:.0f}% dùng)")
    except Exception:
        pass

    # 3. GPU Temp & Compute
    try:
        rc, out, _ = await run_probe_command(
            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu", "--format=csv,noheader"],
            timeout=5.0,
        )
        if rc == 0 and out:
            temp, util = out.decode().strip().split(",")
            lines.append(f"• *GPU Blackwell:* Nhiệt độ `{temp.strip()}°C` | Tải `{util.strip()}`")
    except Exception:
        pass

    lines.append("\n📦 *TRẠNG THÁI CONTAINERS:*")
    try:
        rc, out, err = await run_probe_command(
            ["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"],
            timeout=8.0,
        )
        if rc == 0 and out:
            for c_line in out.decode().strip().split("\n"):
                if not c_line.strip():
                    continue
                parts = c_line.split("|")
                name = parts[0]
                status = parts[1]
                if any(core in name for core in CORE_CONTAINER_KEYWORDS):
                    st_icon = "🟢" if "Up" in status else "🔴"
                    lines.append(f" {st_icon} `{name}`: {status}")
        elif rc != 0:
            lines.append(f"• Lỗi kiểm tra Docker: {escape_md(err.decode().strip() or 'Lệnh quá thời gian hoặc lỗi')}")
    except Exception as e:
        lines.append(f"• Lỗi kiểm tra Docker: {escape_md(str(e))}")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


async def probe_memory_and_swap() -> str:
    """Probes RAM, Swap utilization, swappiness, and top processes by RSS and VmSwap."""
    lines = ["🧠 *CHI TIẾT BỘ NHỚ & SWAP (DGX SPARK)* 🧠\n"]

    # 1. Meminfo
    try:
        with open("/proc/meminfo", "r") as f:
            mem = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    mem[parts[0].strip()] = parts[1].strip()
        total_gb = int(mem.get("MemTotal", "0").split()[0]) / 1024 / 1024
        avail_gb = int(mem.get("MemAvailable", "0").split()[0]) / 1024 / 1024
        used_gb = total_gb - avail_gb
        lines.append(f"• *RAM Vật Lý:* `{used_gb:.1f} GiB / {total_gb:.1f} GiB` (Khả dụng: `{avail_gb:.1f} GiB`)")

        swap_tot_kb = int(mem.get("SwapTotal", "0").split()[0])
        swap_free_kb = int(mem.get("SwapFree", "0").split()[0])
        if swap_tot_kb > 0:
            swap_tot_gb = swap_tot_kb / 1024 / 1024
            swap_used_gb = (swap_tot_kb - swap_free_kb) / 1024 / 1024
            swap_pct = (swap_used_gb / swap_tot_gb) * 100
            lines.append(f"• *Bộ Nhớ Swap:* `{swap_used_gb:.2f} GiB / {swap_tot_gb:.1f} GiB` (`{swap_pct:.1f}%`)")
    except Exception as e:
        lines.append(f"• Lỗi đọc meminfo: {e}")

    # 2. Swappiness
    try:
        with open("/proc/sys/vm/swappiness", "r") as f:
            swappiness = f.read().strip()
        lines.append(f"• *Kernel Swappiness:* `{swappiness}` (Chuẩn tối ưu AI Production: 10)")
    except Exception:
        pass

    # Helper: Docker container mapping & process task resolver
    cmap: Dict[str, str] = {}
    try:
        rc, out, _ = await run_probe_command(
            ["docker", "ps", "-a", "--no-trunc", "--format", "{{.ID}}|{{.Names}}"],
            timeout=8.0,
        )
        if rc == 0 and out:
            for line in out.decode().strip().split("\n"):
                if "|" in line:
                    cid, cname = line.split("|")
                    cmap[cid.strip()] = cname.strip()
    except Exception:
        pass

    def _resolve_pid(pid: str) -> tuple[str, str]:
        cname, task = None, ""
        is_docker = False
        try:
            with open(f"/proc/{pid}/cgroup", "r") as f:
                cg = f.read()
                for line in cg.splitlines():
                    if "docker-" in line or "/docker/" in line:
                        is_docker = True
                        for cid, name in cmap.items():
                            if cid in line:
                                cname = name
                                break
                        if cname:
                            break
                    elif ".service" in line and not cname and not is_docker:
                        parts = [p for p in line.split("/") if p.endswith(".service")]
                        if parts:
                            cname = parts[-1].replace(".service", "")
        except Exception:
            pass

        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                raw = f.read().replace(b"\x00", b" ").decode(errors="ignore").strip()
                if "reindex_milvus" in raw:
                    task = "reindex_milvus.py"
                elif "VLLM::EngineCore" in raw:
                    task = "VLLM::EngineCore"
                elif "pipeline" in raw:
                    task = "ingestion.pipeline"
                elif "uvicorn" in raw:
                    task = "FastAPI / Uvicorn"
                elif "neo4j" in raw or "java" in raw:
                    task = "Neo4j Graph (JVM)"
                elif "litellm" in raw:
                    task = "LiteLLM Gateway"
                elif "ocr" in raw or "surya" in raw:
                    task = "OCR Worker"
                elif "milvus run" in raw:
                    task = "Milvus Standalone"
                elif raw:
                    task = raw.split()[0].split("/")[-1]
        except Exception:
            pass
        origin_icon = "🐳" if is_docker else "💻"
        origin_label = cname if cname else "Host"
        origin = f"{origin_icon} `{origin_label}`"
        return origin, task

    # 3. Top RAM Consumers
    lines.append("\n🔥 *TOP 5 TIẾN TRÌNH DÙNG RAM (RSS):*")
    try:
        rc, out, err = await run_probe_command(
            ["ps", "-eo", "pid,rss", "--sort=-rss"],
            timeout=5.0,
        )
        if rc == 0 and out:
            rows = out.decode().strip().split("\n")[1:6]
            for r in rows:
                p_parts = r.split()
                if len(p_parts) >= 2:
                    pid, rss_kb = p_parts[0], int(p_parts[1])
                    rss_mb = rss_kb / 1024
                    sz_str = f"{rss_mb/1024:.2f} GiB" if rss_mb >= 1024 else f"{rss_mb:.1f} MiB"
                    origin, task = _resolve_pid(pid)
                    lines.append(f"• {origin} (PID {pid}): *{sz_str}*")
                    if task:
                        lines.append(f"  └ `{task.replace('`', '')}`")
        elif rc != 0:
            lines.append(f"• Lỗi đọc tiến trình RAM: {escape_md(err.decode().strip() or 'Timeout hoặc lỗi')}")
    except Exception as e:
        lines.append(f"• Lỗi đọc tiến trình RAM: {escape_md(str(e))}")

    # 4. Top Swap Consumers
    lines.append("\n💾 *TOP 5 TIẾN TRÌNH NẰM TRONG SWAP:*")
    try:
        import glob
        swap_list = []
        for s_file in glob.glob("/proc/[0-9]*/status"):
            try:
                pid = os.path.basename(os.path.dirname(s_file))
                vmswap = 0
                with open(s_file, "r") as f:
                    for s_line in f:
                        if s_line.startswith("VmSwap:"):
                            vmswap = int(s_line.split()[1])
                if vmswap > 0:
                    swap_list.append((vmswap, pid))
            except Exception:
                pass
        swap_list.sort(key=lambda x: (-x[0], int(x[1]) if str(x[1]).isdigit() else x[1]))
        if swap_list:
            for vmswap_kb, pid in swap_list[:5]:
                vmswap_mb = vmswap_kb / 1024
                sz_str = f"{vmswap_mb/1024:.2f} GiB" if vmswap_mb >= 1024 else f"{vmswap_mb:.1f} MiB"
                origin, task = _resolve_pid(pid)
                lines.append(f"• {origin} (PID {pid}): *{sz_str}*")
                if task:
                    lines.append(f"  └ `{task.replace('`', '')}`")
        else:
            lines.append(" 🟢 _Không có tiến trình nào bị trôi vào Swap._")
    except Exception as e:
        lines.append(f"• Lỗi đọc tiến trình Swap: {e}")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


async def _query_litellm_postgres_stats() -> Optional[Dict[str, Any]]:
    """Queries LiteLLM PostgreSQL container for today's ICT local usage statistics via UNION ALL."""
    sql = (
        "(\n"
        "  SELECT 'SUMMARY' AS tag, count(*)::text AS col1, coalesce(sum(total_tokens), 0)::text AS col2,\n"
        "         coalesce(sum(prompt_tokens), 0)::text AS col3, coalesce(sum(completion_tokens), 0)::text AS col4\n"
        '  FROM "LiteLLM_SpendLogs"\n'
        "  WHERE \"startTime\" >= ((CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')::date::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh' AT TIME ZONE 'UTC')\n"
        ")\n"
        "UNION ALL\n"
        "(\n"
        "  SELECT 'MODEL' AS tag, model AS col1, coalesce(sum(total_tokens), 0)::text AS col2, count(*)::text AS col3, '' AS col4\n"
        '  FROM "LiteLLM_SpendLogs"\n'
        "  WHERE \"startTime\" >= ((CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')::date::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh' AT TIME ZONE 'UTC')\n"
        "  GROUP BY model\n"
        "  ORDER BY coalesce(sum(total_tokens), 0) DESC, model ASC\n"
        "  LIMIT 4\n"
        ");"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            LITELLM_PG_CONTAINER,
            "psql",
            "-U",
            LITELLM_PG_USER,
            "-d",
            LITELLM_PG_DATABASE,
            "-t",
            "-A",
            "-F|",
            "-c",
            sql,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return None
        except asyncio.CancelledError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            raise

        if proc.returncode != 0 or not stdout_bytes:
            return None

        summary_data: Dict[str, Any] = {
            "total_requests": 0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "top_models": [],
        }

        for raw_line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split("|")
            tag = parts[0]
            if tag == "SUMMARY" and len(parts) >= 5:
                try:
                    summary_data["total_requests"] = int(parts[1])
                    summary_data["total_tokens"] = int(parts[2])
                    summary_data["prompt_tokens"] = int(parts[3])
                    summary_data["completion_tokens"] = int(parts[4])
                except ValueError:
                    pass
            elif tag == "MODEL" and len(parts) >= 4:
                m_name = parts[1]
                try:
                    m_tok = int(parts[2])
                    m_req = int(parts[3])
                    summary_data["top_models"].append({
                        "model": m_name,
                        "tokens": m_tok,
                        "requests": m_req,
                    })
                except ValueError:
                    pass

        return summary_data
    except asyncio.CancelledError:
        raise
    except Exception:
        return None


def is_account_blocked(account: Dict[str, Any]) -> bool:
    """Checks whether an Antigravity account is blocked, disabled, or in forbidden status."""
    quota = account.get("quota") or {}
    return bool(
        account.get("proxy_disabled")
        or account.get("disabled")
        or account.get("validation_blocked")
        or quota.get("is_forbidden")
    )


def get_antigravity_base_url() -> str:
    """Returns the base URL for Antigravity Tools API, preferring loopback on local host."""
    url = os.environ.get("GATEWAY_PROXY_URL", "http://127.0.0.1:8045").rstrip("/").removesuffix("/v1")
    tailscale_ip = os.environ.get("TAILSCALE_SPARK_IP", "100.83.192.30")  # ccba:allow-raw-ip
    if tailscale_ip in url:
        return url.replace(tailscale_ip, "127.0.0.1")
    return url


async def probe_gateway_stats() -> str:
    """Queries Antigravity Tools API (Cloud) and LiteLLM Postgres (Local GPU) for unified stats."""
    lines = ["📈 *BÁO CÁO SẢN LƯỢNG AI GATEWAY* 📈\n"]
    base_url = get_antigravity_base_url()
    key = os.environ.get("GATEWAY_ADMIN_PASSWORD") or os.environ.get("GATEWAY_PROXY_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    cloud_req = 0
    cloud_tok = 0
    cloud_in = 0
    cloud_out = 0

    # 1. Cloud Proxy (:8045)
    lines.append("☁️ *CỔNG CLOUD (:8045)*")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{base_url}/api/stats/token/summary", headers=headers)
            if res.status_code == 200:
                s = res.json()
                cloud_req = s.get("total_requests") or 0
                cloud_tok = s.get("total_tokens") or 0
                cloud_in = s.get("total_input_tokens") or 0
                cloud_out = s.get("total_output_tokens") or 0
                lines.append(f"• *Requests:* `{cloud_req:,}` | *Tokens:* `{cloud_tok:,}`")
                lines.append(f"• *Input:* `{cloud_in:,}` | *Output:* `{cloud_out:,}`")
            else:
                lines.append(f"• Không thể tải số liệu tổng hợp (HTTP {res.status_code})")

            res_m = await client.get(f"{base_url}/api/stats/token/by-model", headers=headers)
            if res_m.status_code == 200:
                models = res_m.json()
                if isinstance(models, list) and models:
                    lines.append("• *Top Mô Hình Cloud:*")
                    # Rule 5: Multi-Key Deterministic Sorting
                    sorted_models = sorted(
                        models,
                        key=lambda m: (-int(m.get("total_tokens") or 0), str(m.get("model") or "")),
                    )
                    for m in sorted_models[:4]:
                        m_name = str(m.get("model") or "unknown").replace("`", "'")
                        m_tok = int(m.get("total_tokens") or 0)
                        m_req = int(m.get("request_count") or 0)
                        lines.append(f"  └─ `{m_name}`: `{m_tok:,}` tokens (`{m_req}` reqs)")

            res_acc = await client.get(f"{base_url}/api/accounts", headers=headers)
            if res_acc.status_code == 200:
                data = res_acc.json()
                accounts = data.get("accounts", []) if isinstance(data, dict) else []
                active = sum(1 for a in accounts if not is_account_blocked(a))
                lines.append(f"• *Quota Pool:* `{active}/{len(accounts)}` tài khoản khả dụng")
    except Exception as e:
        clean_err = str(e).replace("`", "'")
        lines.append(f"• Lỗi kết nối Antigravity Tools API: `{clean_err}`")

    # 2. Local GPU (:8090 - LiteLLM Postgres)
    lines.append("\n🖥️ *CỔNG GPU CỤC BỘ (:8090)*")
    local_stats = await _query_litellm_postgres_stats()
    local_req = 0
    local_tok = 0
    local_in = 0
    local_out = 0

    if local_stats is not None:
        local_req = local_stats.get("total_requests") or 0
        local_tok = local_stats.get("total_tokens") or 0
        local_in = local_stats.get("prompt_tokens") or 0
        local_out = local_stats.get("completion_tokens") or 0
        lines.append(f"• *Requests:* `{local_req:,}` | *Tokens:* `{local_tok:,}`")
        lines.append(f"• *Input:* `{local_in:,}` | *Output:* `{local_out:,}`")
        top_local = local_stats.get("top_models", [])
        if top_local:
            lines.append("• *Top Mô Hình Cục Bộ:*")
            for m in top_local:
                m_name = str(m.get("model") or "unknown").replace("`", "'")
                m_t = int(m.get("tokens") or 0)
                m_r = int(m.get("requests") or 0)
                lines.append(f"  └─ `{m_name}`: `{m_t:,}` tokens (`{m_r}` reqs)")
    else:
        lines.append("• Không thể truy vấn LiteLLM Postgres cục bộ")

    # 3. Aggregate Summary
    lines.append("\n📊 *TỔNG HỢP TOÀN HỆ THỐNG*")
    total_req = cloud_req + local_req
    total_tok = cloud_tok + local_tok
    offload_ratio = (local_tok / total_tok * 100.0) if total_tok > 0 else 0.0
    lines.append(f"• *Tổng Requests:* `{total_req:,}`")
    lines.append(f"• *Tổng Tokens:* `{total_tok:,}`")
    lines.append(f"• *Tỷ Lệ Tải Cục Bộ (Offload):* `{offload_ratio:.1f}%`")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


def extract_validation_url(account_data: Dict[str, Any]) -> Optional[str]:
    """Extracts Google verification URL from account metadata or error strings."""
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


def render_health_bar(active: int, total: int, width: int = 10) -> str:
    """Renders a Unicode visual health bar for account pool."""
    if total <= 0:
        return f"[{'⬛' * width}]"
    ratio = min(max(active / total, 0.0), 1.0)
    green_blocks = int(round(ratio * width))
    red_blocks = width - green_blocks
    bar = "🟩" * green_blocks + "🟥" * red_blocks
    pct = int(round(ratio * 100))
    return f"[{bar}] `{active}/{total}` ({pct}%)"


def format_blocked_accounts(blocked_list: list) -> list[str]:
    """Formats blocked accounts into distinct triage categories."""
    lines: list[str] = ["⚠️ *Tài khoản bị ngắt kết nối:*"]
    challenge_accounts = []
    manual_accounts = []
    cooldown_accounts = []

    for b in blocked_list:
        val_url = extract_validation_url(b)
        b_reason = str(b.get("proxy_disabled_reason") or b.get("disabled_reason") or "403 Forbidden")
        if val_url or b.get("validation_blocked") or "verify your account" in b_reason.lower():
            challenge_accounts.append((b, val_url))
        elif "disabled manually by user" in b_reason.lower() or b.get("disabled"):
            manual_accounts.append(b)
        else:
            cooldown_accounts.append((b, b_reason))

    if challenge_accounts:
        lines.append("  *Cần xác minh danh tính (Browser Challenge):*")
        for b, val_url in challenge_accounts:
            b_email = b.get("email")
            if val_url:
                lines.append(f"  └─ 🟡 `{b_email}`: [🔗 Xác minh ngay]({val_url})")
            else:
                lines.append(f"  └─ 🟡 `{b_email}`: Cần xác minh trình duyệt")

    if manual_accounts:
        lines.append("  *Đang tắt thủ công:*")
        for b in manual_accounts:
            b_email = b.get("email")
            b_id = b.get("id")
            lines.append(f"  └─ ⚪ `{b_email}`: Đã tắt tay (Dùng `/reenable_account {b_id}`)")

    if cooldown_accounts:
        lines.append("  *Đang hạ nhiệt Quota:*")
        for b, b_reason in cooldown_accounts:
            b_email = b.get("email")
            r_desc = "Warmup 403 Forbidden" if "quota fetch denied" in b_reason else b_reason[:40]
            lines.append(f"  └─ 🔴 `{b_email}`: {r_desc}")

    return lines


async def probe_antigravity_status() -> str:
    """Queries Antigravity Tools API (:8045) for account pool health and blocked states."""
    base_url = get_antigravity_base_url()
    key = os.environ.get("GATEWAY_ADMIN_PASSWORD") or os.environ.get("GATEWAY_PROXY_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    lines = ["🤖 *HỒ BƠI TÀI KHOẢN ANTIGRAVITY TOOLS* 🤖\n"]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            h_res = await client.get(f"{base_url}/healthz")
            if h_res.status_code == 200:
                lines.append("• *Trạng thái:* 🟢 Online (`:8045`) | Mode: `CacheFirst`")
            else:
                lines.append(f"• *Trạng thái:* 🔴 HTTP {h_res.status_code}")

            a_res = await client.get(f"{base_url}/api/accounts", headers=headers)
            if a_res.status_code == 200:
                data = a_res.json()
                accounts = data.get("accounts", []) if isinstance(data, dict) else data
                total = len(accounts)
                active_list = []
                blocked_list = []

                for a in accounts:
                    if is_account_blocked(a):
                        blocked_list.append(a)
                    else:
                        active_list.append(a)

                health_bar = render_health_bar(len(active_list), total)
                lines.append(f"• *Hồ bơi tài khoản:* {health_bar}\n")

                if blocked_list:
                    lines.extend(format_blocked_accounts(blocked_list))
                    lines.append("")

                lines.append("✅ *Tài khoản hoạt động:*")
                for act in active_list:
                    lines.append(f"  └─ 🟢 `{act.get('email')}`")
            else:
                lines.append(f"• Không thể đọc danh sách tài khoản (HTTP {a_res.status_code})")
    except Exception as e:
        clean_err = str(e).replace("`", "'")
        lines.append(f"• Lỗi kết nối Antigravity Tools: `{clean_err}`")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


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


async def reenable_antigravity_account(
    account_id: str,
    chat_id: int,
    status_msg_id: int,
    cq_id: Optional[str] = None,
    user_id: int = ADMIN_USER_ID,
) -> bool:
    """Executes a 4-stage Health Probe Gate before safely re-enabling an Antigravity account."""
    if cq_id:
        await answer_callback(cq_id, f"🔍 Đang kiểm tra probe {account_id}...")

    t0 = time.time()
    base_url = get_antigravity_base_url()
    key = os.environ.get("GATEWAY_ADMIN_PASSWORD") or os.environ.get("GATEWAY_PROXY_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    client = get_http_client()

    # --- CHỐT CHẶN 1: Local Pre-Classification (Không gọi Upstream bừa bãi) ---
    target_account: Optional[Dict[str, Any]] = None
    try:
        acc_list_res = await client.get(f"{base_url}/api/accounts", headers=headers, timeout=5.0)
        if acc_list_res.status_code != 200:
            duration_ms = int((time.time() - t0) * 1000)
            fail_msg = f"🔒 *LỖI KẾT NỐI LOCAL API*\n\nKhông thể đọc danh sách tài khoản từ máy chủ local (HTTP {acc_list_res.status_code})."
            if not await edit_telegram_msg(chat_id, status_msg_id, fail_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, fail_msg, reply_markup=get_main_dashboard_markup())
            append_audit_log(
                "antigravity_reenable",
                "antigravity.account.reenable",
                {"account_id": account_id, "error": f"HTTP {acc_list_res.status_code}"},
                user_id,
                "PRE_CHECK_REJECTED",
                duration_ms,
                1,
                "Local accounts API unavailable",
            )
            return False

        data = acc_list_res.json()
        accs = data.get("accounts", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for a in accs:
            if str(a.get("id")) == str(account_id) or str(a.get("email")) == str(account_id):
                target_account = a
                account_id = str(a.get("id"))
                break

        if not target_account:
            duration_ms = int((time.time() - t0) * 1000)
            fail_msg = f"🔒 *TÀI KHOẢN KHÔNG TỒN TẠI*\n\nKhông tìm thấy tài khoản `{account_id}` trong hệ thống quản trị local."
            if not await edit_telegram_msg(chat_id, status_msg_id, fail_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, fail_msg, reply_markup=get_main_dashboard_markup())
            append_audit_log(
                "antigravity_reenable",
                "antigravity.account.reenable",
                {"account_id": account_id},
                user_id,
                "PRE_CHECK_REJECTED",
                duration_ms,
                1,
                "Account not found in local pool",
            )
            return False

        raw_reason = str(
            target_account.get("disabled_reason")
            or target_account.get("proxy_disabled_reason")
            or target_account.get("validation_blocked_reason")
            or (target_account.get("quota") or {}).get("forbidden_reason")
            or ""
        )
        val_url = extract_validation_url(target_account)
        has_val_url = bool(val_url or "accounts.google.com/signin/continue" in raw_reason)
        is_disabled = bool(target_account.get("disabled"))
        is_challenge = bool(
            target_account.get("validation_blocked")
            or has_val_url
            or any(kw in raw_reason.lower() for kw in [
                "verify your account", "validation_required", "invalid_grant", "unauthorized_client"
            ])
        )

        # Chặn đứng probe nếu tài khoản có Challenge bảo mật hoặc bị Disabled toàn hệ thống
        if is_challenge or is_disabled:
            duration_ms = int((time.time() - t0) * 1000)
            if is_challenge:
                reason_desc = "Cần mở khóa thủ công trên trình duyệt"
                action_hint = f"👉 [🔗 Bấm vào đây để mở trang xác minh Google]({val_url})" if val_url else "👉 Vui lòng hoàn thành xác thực trình duyệt trên máy chủ."
            else:
                reason_desc = "Tài khoản đã bị vô hiệu hóa (disabled)"
                action_hint = "👉 Vui lòng kiểm tra lại cấu hình tài khoản trên máy chủ."

            reject_msg = (
                f"🔒 *TỪ CHỐI HEALTH PROBE (CHỐT CHẶN LOCAL BẢO VỆ)*\n\n"
                f"• **Tài khoản**: `{account_id}` ({target_account.get('email', 'N/A')})\n"
                f"• **Nguyên nhân**: {reason_desc}\n"
                f"• **Quyết định**: **Chặn probe upstream** để ngăn Google đánh cờ (flag) tài khoản lạm dụng.\n\n"
                f"{action_hint}"
            )
            if not await edit_telegram_msg(chat_id, status_msg_id, reject_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, reject_msg, reply_markup=get_main_dashboard_markup())
            append_audit_log(
                "antigravity_reenable",
                "antigravity.account.reenable",
                {"account_id": account_id, "reason": raw_reason},
                user_id,
                "PRE_CHECK_REJECTED",
                duration_ms,
                1,
                f"Pre-check blocked upstream probe: {reason_desc}",
            )
            return False
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        fail_msg = f"🔒 *LỖI NGOẠI LỆ PRE-CHECK*\n\nĐã chặn probe upstream do lỗi pre-check: {e}"
        if not await edit_telegram_msg(chat_id, status_msg_id, fail_msg, reply_markup=get_main_dashboard_markup()):
            await send_telegram_msg(chat_id, fail_msg, reply_markup=get_main_dashboard_markup())
        append_audit_log(
            "antigravity_reenable",
            "antigravity.account.reenable",
            {"account_id": account_id, "error": str(e)},
            user_id,
            "PRE_CHECK_REJECTED",
            duration_ms,
            1,
            f"Pre-check exception: {e}",
        )
        return False

    # --- CHỐT CHẶN 2: Quota Probe Gate (GET /api/accounts/{id}/quota) ---
    quota_url = f"{base_url}/api/accounts/{account_id}/quota"
    toggle_url = f"{base_url}/api/accounts/{account_id}/toggle-proxy"

    try:
        quota_res = await client.get(quota_url, headers=headers, timeout=30.0)
        quota_code = quota_res.status_code
        q_data = None
        if quota_code == 200:
            try:
                q_data = quota_res.json()
            except Exception:
                q_data = None

        is_allowed = quota_probe_allows_toggle(q_data) if quota_code == 200 else False

        if not is_allowed:
            duration_ms = int((time.time() - t0) * 1000)
            forbidden_reason = ""
            if isinstance(q_data, dict):
                forbidden_reason = str(q_data.get("forbidden_reason") or (q_data.get("quota") or {}).get("forbidden_reason") or "")
            if quota_code == 401:
                detail = "Admin Secret không hợp lệ (HTTP 401 Unauthorized)"
            elif quota_code == 404:
                detail = f"Không tìm thấy tài khoản `{account_id}` (HTTP 404 Not Found)"
            elif forbidden_reason:
                detail = f"Google Cloud Code vẫn chặn (403 Forbidden: {forbidden_reason[:60]})"
            elif quota_code == 200:
                detail = "Phản hồi quota upstream không hợp lệ hoặc thiếu cờ khả dụng"
            else:
                detail = f"Mã phản hồi HTTP {quota_code}"

            fail_msg = (
                f"🔒 *HEALTH PROBE THẤT BẠI (GOOGLE UPSTREAM REJECTED)*\n\n"
                f"• **Tài khoản**: `{account_id}`\n"
                f"• **Chi tiết**: {detail}\n"
                f"• **Quyết định**: **Giữ nguyên trạng thái ngắt kết nối** để bảo vệ tài khoản.\n\n"
                f"👉 *Hướng dẫn*: Vui lòng kiểm tra lại trạng thái tài khoản trên máy chủ."
            )
            if not await edit_telegram_msg(chat_id, status_msg_id, fail_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, fail_msg, reply_markup=get_main_dashboard_markup())
            append_audit_log(
                "antigravity_reenable",
                "antigravity.account.reenable",
                {"account_id": account_id, "quota_code": str(quota_code), "probe_allowed": is_allowed},
                user_id,
                "PROBE_FAILED",
                duration_ms,
                1,
                f"Probe rejected: {detail}",
            )
            return False

        # --- CHỐT CHẶN 3: Kích Hoạt Proxy (POST /api/accounts/{id}/toggle-proxy) ---
        enable_res = await client.post(toggle_url, headers=headers, json={"enable": True}, timeout=10.0)
        duration_ms = int((time.time() - t0) * 1000)

        if enable_res.status_code == 200:
            success_msg = (
                f"✅ *XÁC THỰC THÀNH CÔNG (HEALTH PROBE PASSED)*\n\n"
                f"• **Tài khoản**: `{account_id}`\n"
                f"• **Health Probe**: HTTP `200 OK` (Google Quota xác nhận sạch)\n"
                f"• **Trạng thái Pool**: 🟢 Đã kích hoạt lại thành công (Active in RAM Rotation)\n"
                f"• **Thời gian**: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}"
            )
            if not await edit_telegram_msg(chat_id, status_msg_id, success_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, success_msg, reply_markup=get_main_dashboard_markup())
            append_audit_log(
                "antigravity_reenable",
                "antigravity.account.reenable",
                {"account_id": account_id, "probe": 200, "toggle_proxy": 200},
                user_id,
                "SUCCESS",
                duration_ms,
                0,
                "Account re-enabled after passing quota probe and toggle proxy",
            )
            return True
        else:
            enable_err_msg = (
                f"⚠️ *PROBE THÀNH CÔNG NHƯNG BẬT LẠI THẤT BẠI*\n\n"
                f"• **Tài khoản**: `{account_id}`\n"
                f"• **Probe**: HTTP `200 OK`\n"
                f"• **Lỗi Toggle Proxy**: HTTP `{enable_res.status_code}`\n"
                f"• Vui lòng kiểm tra lại dịch vụ Antigravity Tools."
            )
            if not await edit_telegram_msg(chat_id, status_msg_id, enable_err_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, enable_err_msg, reply_markup=get_main_dashboard_markup())
            append_audit_log(
                "antigravity_reenable",
                "antigravity.account.reenable",
                {"account_id": account_id, "probe": 200, "enable": enable_res.status_code},
                user_id,
                "ENABLE_FAILED",
                duration_ms,
                1,
                f"Toggle proxy returned HTTP {enable_res.status_code}",
            )
            return False

    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        net_err_msg = f"❌ *LỖI KẾT NỐI KHI BẬT LẠI TÀI KHOẢN*: {e}"
        if not await edit_telegram_msg(chat_id, status_msg_id, net_err_msg, reply_markup=get_main_dashboard_markup()):
            await send_telegram_msg(chat_id, net_err_msg, reply_markup=get_main_dashboard_markup())
        append_audit_log(
            "antigravity_reenable",
            "antigravity.account.reenable",
            {"account_id": account_id, "error": str(e)},
            user_id,
            "ERROR",
            duration_ms,
            1,
            str(e),
        )
        return False


async def probe_blackwell_gpu() -> str:
    """Deep probe for NVIDIA GB10 with compute processes memory summation."""
    lines = ["🎮 *THÔNG SỐ GPU NVIDIA BLACKWELL GB10* 🎮\n"]
    try:
        rc1, out1, _ = await run_probe_command(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,power.draw",
                "--format=csv,noheader",
            ],
            timeout=5.0,
        )
        if rc1 == 0 and out1:
            name, temp, util, power = [x.strip() for x in out1.decode().strip().split(",")]
            lines.append(f"• Thiết bị: `{name}`")
            lines.append(f"• Nhiệt độ: `{temp}°C` | Tải: `{util}` | Công suất: `{power}`")

        # Query compute processes
        rc2, out2, _ = await run_probe_command(
            [
                "nvidia-smi",
                "--query-compute-apps=process_name,used_memory",
                "--format=csv,noheader",
            ],
            timeout=5.0,
        )
        apps = []
        total_used_mib = 0.0
        if rc2 == 0 and out2:
            for row in out2.decode().strip().split("\n"):
                if not row.strip():
                    continue
                p_parts = [x.strip() for x in row.split(",")]
                if len(p_parts) == 2:
                    p_name = p_parts[0].split("/")[-1]
                    m_str = p_parts[1].replace("MiB", "").strip()
                    try:
                        m_val = float(m_str)
                        total_used_mib += m_val
                        apps.append(f"  └─ `{p_name}`: {m_val/1024:.1f} GiB")
                    except ValueError:
                        pass

        lines.append(f"• Bộ nhớ tính toán: `{total_used_mib/1024:.1f} GiB / 128.0 GiB (Unified Memory)`")
        if apps:
            lines.append("• Tiến trình GPU đang dùng:")
            lines.extend(apps[:5])
        else:
            lines.append("• Không có tiến trình GPU compute nào đang chạy.")
    except Exception as e:
        lines.append(f"• Lỗi truy vấn GPU: {escape_md(str(e))}")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


async def execute_shell_job(
    cmd: str | list[str],
    job_id: str,
    chat_id: int,
    status_msg_id: int,
    title: str,
    timeout: int = 120,
    use_shell: bool = False,
) -> None:
    """Executes a subprocess with real-time feedback and Two-Tier Delivery."""
    start_time = time.time()
    await edit_telegram_msg(chat_id, status_msg_id, f"⏳ *[ĐANG CHẠY]* `{title}`\nJob ID: `{job_id}`\nVui lòng đợi...")

    try:
        if use_shell:
            shell_cmd = cmd if isinstance(cmd, str) else " ".join(cmd)
            proc = await asyncio.create_subprocess_shell(
                shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                start_new_session=True,
                cwd=str(PROJECT_ROOT),
            )
        else:
            argv = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
            proc = await asyncio.create_subprocess_exec(
                argv[0],
                *argv[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                start_new_session=True,
                cwd=str(PROJECT_ROOT),
            )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
            except Exception:
                pass
            dur = int((time.time() - start_time) * 1000)
            await edit_telegram_msg(
                chat_id,
                status_msg_id,
                f"❌ *[TIMEOUT]* `{title}`\nJob bị hủy do vượt quá {timeout}s!\nThời gian: {dur/1000:.1f}s",
            )
            append_audit_log("exec", cmd, {"job_id": job_id}, ADMIN_USER_ID, "TIMEOUT", dur, -1, "Process killed on timeout")
            return
        except asyncio.CancelledError:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
            except Exception:
                pass
            raise

        duration_ms = int((time.time() - start_time) * 1000)
        exit_code = proc.returncode or 0
        out_text = (stdout_bytes or b"").decode("utf-8", errors="replace")
        err_text = (stderr_bytes or b"").decode("utf-8", errors="replace")
        full_output = (out_text + "\n" + err_text).strip()

        log_file = LOG_DIR / f"job_{job_id}_{int(time.time())}.log"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"Command: {cmd}\nExit Code: {exit_code}\nDuration: {duration_ms}ms\n\n{full_output}")

        # Guard against swallowed errors (Exit 0 but fatal error markers present)
        is_suspicious_success = (
            exit_code == 0
            and any(
                marker in full_output
                for marker in [
                    "[ERROR] ccba.eval",
                    "❌ Lỗi trong quá trình",
                    "Traceback (most recent call last):",
                ]
            )
        )

        if is_suspicious_success:
            status_icon = "⚠️"
            status_text = "CẢNH BÁO (CÓ LỖI XUẤT HIỆN TRONG LOG)"
        else:
            status_icon = "✅" if exit_code == 0 else "❌"
            status_text = "THÀNH CÔNG" if exit_code == 0 else f"THẤT BẠI (Exit {exit_code})"

        # Two-Tier Output Logic
        if len(full_output) <= 2000 and exit_code == 0 and not is_suspicious_success:
            res_msg = (
                f"{status_icon} *[{status_text}]* `{title}`\n"
                f"• Thời gian: `{duration_ms/1000:.1f}s` | Exit: `{exit_code}`\n\n"
                f"```\n{full_output[:1500]}\n```"
            )
            await edit_telegram_msg(chat_id, status_msg_id, res_msg)
        else:
            tail_lines = full_output.split("\n")[-12:]
            res_msg = (
                f"{status_icon} *[{status_text}]* `{title}`\n"
                f"• Thời gian: `{duration_ms/1000:.1f}s` | Exit: `{exit_code}`\n"
                f"• Chi tiết: Đã đính kèm file log bên dưới.\n\n"
                f"```\n" + "\n".join(tail_lines) + "\n```"
            )
            await edit_telegram_msg(chat_id, status_msg_id, res_msg)
            await send_telegram_document(chat_id, log_file, caption=f"Log chi tiết: {title} (Job: {job_id})")

        audit_status = "WARNING" if is_suspicious_success else ("SUCCESS" if exit_code == 0 else "FAILED")
        append_audit_log("exec", cmd, {"job_id": job_id}, ADMIN_USER_ID, audit_status, duration_ms, exit_code, full_output[:200])

    except Exception as e:
        dur = int((time.time() - start_time) * 1000)
        await edit_telegram_msg(chat_id, status_msg_id, f"❌ *[LỖI THỰC THI]* `{title}`\nLỗi: {e}")
        append_audit_log("exec", cmd, {"job_id": job_id}, ADMIN_USER_ID, "ERROR", dur, -1, str(e))


# --- 6. EMERGENCY SHELL GUARDRAILS ---
def check_brute_force_lockout() -> Optional[int]:
    """Checks if /exec is locked out. Returns remaining seconds or None."""
    if not LOCKOUT_FILE.exists():
        return None
    try:
        data = json.loads(LOCKOUT_FILE.read_text())
        locked_until = data.get("locked_until", 0)
        now = time.time()
        if now < locked_until:
            return int(locked_until - now)
    except Exception:
        pass
    return None


def register_failed_pin_attempt() -> int:
    """Increments failed PIN attempts and locks out if >= 3. Returns attempts count."""
    data = {"attempts": 0, "locked_until": 0}
    if LOCKOUT_FILE.exists():
        try:
            data = json.loads(LOCKOUT_FILE.read_text())
        except Exception:
            pass

    old_locked_until = data.get("locked_until", 0)
    if old_locked_until > 0 and time.time() >= old_locked_until:
        data["attempts"] = 0
        data["locked_until"] = 0
        append_audit_log("exec", "lockout_expired", {}, ADMIN_USER_ID, "RESET", 0, 0, "Brute force lockout expired, counter reset")

    attempts = data.get("attempts", 0) + 1
    locked_until = 0
    if attempts >= 3:
        locked_until = int(time.time() + 3600)  # 1 hour lockout
    data = {"attempts": attempts, "locked_until": locked_until}
    LOCKOUT_FILE.write_text(json.dumps(data))
    return attempts


def reset_failed_pin_attempts() -> None:
    """Resets failed PIN counter upon success."""
    if LOCKOUT_FILE.exists():
        LOCKOUT_FILE.write_text(json.dumps({"attempts": 0, "locked_until": 0}))


# --- 7. DASHBOARD MENUS BUILDER ---
def get_main_dashboard_markup() -> Dict[str, Any]:
    """Builds the main interactive dashboard keyboard (12 buttons, 6 rows)."""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Xem Toàn Bộ Status", "callback_data": "menu:status"},
                {"text": "🧠 Bộ Nhớ & Swap", "callback_data": "menu:memory"},
            ],
            [
                {"text": "🎮 GPU Blackwell", "callback_data": "menu:gpu"},
                {"text": "📈 Sản Lượng Token (Dual)", "callback_data": "menu:stats"},
            ],
            [
                {"text": "🔄 Khởi Động Lại Service", "callback_data": "menu:restart_list"},
                {"text": "📦 Cập Nhật Open WebUI", "callback_data": "menu:upgrade_owu"},
            ],
            [
                {"text": "🌙 Auto-Tuner CCBA (MỚI)", "callback_data": "menu:autotuner"},
                {"text": "⚡ Can Thiệp /boost (MỚI)", "callback_data": "menu:boost_list"},
            ],
            [
                {"text": "📄 Hàng Đợi RAG Ingestion", "callback_data": "menu:rag_state"},
                {"text": "📦 Quản Lý Phụ Thuộc (MỚI)", "callback_data": "menu:deps_menu"},
            ],
            [
                {"text": "🤖 Hồ Bơi Antigravity", "callback_data": "menu:antigravity"},
                {"text": "❓ Hướng Dẫn ChatOps", "callback_data": "menu:help"},
            ],
            [
                {"text": "⚡ Đổi Model Grok CLI (MỚI)", "callback_data": "menu:grok_menu"},
            ],
        ]
    }


def get_grok_menu_markup(current_model: str = "") -> Dict[str, Any]:
    """Builds sub-menu for switching Grok Build CLI default model."""
    keyboard = []
    for i in range(0, len(GROK_AVAILABLE_MODELS), 2):
        row = []
        for m_id, label in GROK_AVAILABLE_MODELS[i:i + 2]:
            display = f"{label} ✅" if m_id == current_model else label
            row.append({"text": display, "callback_data": f"grok_set:{m_id}"})
        keyboard.append(row)

    keyboard.append([
        {"text": "🎯 Mức Suy Luận (Effort)", "callback_data": "menu:grok_effort_menu"},
        {"text": "🔄 Làm Mới", "callback_data": "menu:grok_menu"},
    ])
    keyboard.append([
        {"text": "🔙 Quay Lại Menu Chính", "callback_data": "menu:main"},
    ])
    return {"inline_keyboard": keyboard}


def get_grok_effort_markup(current_effort: str = "") -> Dict[str, Any]:
    """Builds sub-menu for choosing Grok reasoning effort."""
    keyboard = []
    for i in range(0, len(GROK_EFFORT_LEVELS), 2):
        row = []
        for eff_id, label in GROK_EFFORT_LEVELS[i:i + 2]:
            display = f"{label} ✅" if eff_id == current_effort else label
            row.append({"text": display, "callback_data": f"grok_effort:{eff_id}"})
        keyboard.append(row)

    keyboard.append([
        {"text": "🔙 Quay Lại Menu Grok", "callback_data": "menu:grok_menu"},
    ])
    return {"inline_keyboard": keyboard}


def get_grok_config_path() -> Path:
    """Returns the path to ~/.grok/config.toml."""
    return GROK_CONFIG_PATH


def read_grok_model_info() -> Dict[str, Any]:
    """Reads current model and effort from ~/.grok/config.toml."""
    cfg_path = get_grok_config_path()
    if not cfg_path.exists():
        return {"default": "unknown", "effort": "unknown", "exists": False}
    try:
        content = cfg_path.read_text(encoding="utf-8")
        data = tomllib.loads(content)
        models_cfg = data.get("models", {})
        return {
            "default": str(models_cfg.get("default", "grok-4.7")),
            "effort": str(models_cfg.get("default_reasoning_effort", "xhigh")),
            "exists": True,
        }
    except Exception as e:
        return {"default": "error", "effort": "error", "exists": True, "error": str(e)}


def format_grok_menu_text() -> str:
    """Formats Markdown text describing current Grok Build model status."""
    info = read_grok_model_info()
    cur_model = info.get("default", "unknown")
    cur_effort = info.get("effort", "unknown")

    model_display_names = {
        "qwen-local": "Qwen 35B Local (GPU Spark - Miễn phí)",
        "gemini-38-flash": "Gemini 3.8 Flash High (AI Gateway)",
        "claude-sonnet-4-6": "Claude Sonnet 4.6 (AI Gateway)",
        "claude-opus-4-6": "Claude Opus 4.6 (AI Gateway)",
        "grok-4.7": "Grok 4.7 (xAI Frontier - Weekly Limit)",
        "grok-4.7-build-fast": "Grok 4.7 Fast (xAI)",
        "grok-4.6": "Grok 4.6 (xAI)",
        "grok-4.5": "Grok 4.5 (xAI)",
    }
    disp = model_display_names.get(cur_model, cur_model)

    return (
        "⚡ *QUẢN LÝ MODEL GROK BUILD CLI* ⚡\n\n"
        f"• *Model hiện tại:* `{disp}`\n"
        f"• *Mức suy luận (Effort):* `{cur_effort}`\n"
        f"• *Cấu hình:* `~/.grok/config.toml`\n\n"
        "👇 _Chọn model bên dưới để chuyển đổi ngay lập tức cho Grok Build:_"
    )


def format_grok_effort_text() -> str:
    """Formats Markdown text describing reasoning effort selection."""
    info = read_grok_model_info()
    cur_model = info.get("default", "unknown")
    cur_effort = info.get("effort", "unknown")

    return (
        "🎯 *CHỌN MỨC SUY LUẬN (REASONING EFFORT)* 🎯\n\n"
        f"• *Model đang dùng:* `{cur_model}`\n"
        f"• *Mức suy luận hiện tại:* `{cur_effort}`\n\n"
        "👇 _Chọn mức độ suy luận bên dưới:_"
    )


def update_grok_model(new_model: str) -> bool:
    """Updates default model under [models] in ~/.grok/config.toml safely."""
    cfg_path = get_grok_config_path()
    if not cfg_path.exists():
        return False
    try:
        content = cfg_path.read_text(encoding="utf-8")
        if re.search(r'(?m)^\s*default\s*=', content):
            new_content = re.sub(
                r'(?m)^(\s*default\s*=\s*")[^"]*(")',
                rf'\g<1>{new_model}\g<2>',
                content,
            )
        else:
            new_content = re.sub(
                r'(?m)^(\[models\]\s*$)',
                rf'\g<1>\ndefault = "{new_model}"',
                content,
            )
        # Verify TOML syntax before writing
        parsed = tomllib.loads(new_content)
        if parsed.get("models", {}).get("default") != new_model:
            return False
        cfg_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception:
        return False


def update_grok_effort(new_effort: str) -> bool:
    """Updates default_reasoning_effort under [models] in ~/.grok/config.toml safely."""
    cfg_path = get_grok_config_path()
    if not cfg_path.exists():
        return False
    try:
        content = cfg_path.read_text(encoding="utf-8")
        if re.search(r'(?m)^\s*default_reasoning_effort\s*=', content):
            new_content = re.sub(
                r'(?m)^(\s*default_reasoning_effort\s*=\s*")[^"]*(")',
                rf'\g<1>{new_effort}\g<2>',
                content,
            )
        else:
            new_content = re.sub(
                r'(?m)^(\[models\]\s*$)',
                rf'\g<1>\ndefault_reasoning_effort = "{new_effort}"',
                content,
            )
        # Verify TOML syntax before writing
        parsed = tomllib.loads(new_content)
        if parsed.get("models", {}).get("default_reasoning_effort") != new_effort:
            return False
        cfg_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception:
        return False


def get_deps_menu_markup() -> Dict[str, Any]:
    """Builds sub-menu for dependency management and 1-click upgrades."""
    return {
        "inline_keyboard": [
            [
                {"text": "🔍 Rà Soát Độ Trễ & CVE (/deps)", "callback_data": "menu:deps_check"},
            ],
            [
                {"text": "⚡ Nâng Cấp Tier 1 (Patch)", "callback_data": "menu:deps_upg_patch"},
                {"text": "🚀 Nâng Cấp Tier 2 (Minor)", "callback_data": "menu:deps_upg_minor"},
            ],
            [
                {"text": "🔙 Quay Lại Menu Chính", "callback_data": "menu:main"},
            ],
        ]
    }


def get_restart_service_markup() -> Dict[str, Any]:
    """Builds sub-menu for restarting services."""
    services = [
        "open-webui",
        "qwen36b",
        "ai-gateway",
        "smart-watchdog",
        "cloudflared-tunnel",
        "rag-service",
        "milvus-standalone",
        "neo4j-graph",
        "dgx-spark-ocr-worker",
        "rag-frontend",
        "whisper-local",
    ]
    keyboard = []
    for i in range(0, len(services), 2):
        row = [{"text": f"🔄 {services[i]}", "callback_data": f"rst:{services[i]}"}]
        if i + 1 < len(services):
            row.append({"text": f"🔄 {services[i+1]}", "callback_data": f"rst:{services[i+1]}"})
        keyboard.append(row)
    keyboard.append([{"text": "🔙 Quay Lại Menu Chính", "callback_data": "menu:main"}])
    return {"inline_keyboard": keyboard}


def get_boost_skills_markup(
    escalations_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds single-column mobile-friendly keyboard for top 6 plateau skills."""
    if escalations_dir is None:
        hub_base = os.environ.get("CCBA_HUB_PATH", str(Path.home() / "ccba/ccba-agent-platform"))
        escalations_dir = os.path.join(hub_base, ".md", "knowledge", "escalations")
    p_dir = Path(escalations_dir)
    keyboard = []
    if p_dir.exists() and p_dir.is_dir():
        files = [p for p in p_dir.glob("*_plateau.md") if p.is_file()]

        def _safe_mtime(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0

        # Rule 5: Multi-Key Deterministic Sorting
        files.sort(key=lambda p: (-_safe_mtime(p), p.name))
        for p in files[:6]:
            skill_name = p.name.removesuffix("_plateau.md").strip()
            if skill_name:
                keyboard.append([{"text": f"🚀 {skill_name}", "callback_data": f"bst:{skill_name}"}])

    if not keyboard:
        keyboard.append([{"text": "ℹ️ Không có kỹ năng plateau", "callback_data": "menu:main"}])

    keyboard.append([{"text": "🔙 Quay Lại Menu Chính", "callback_data": "menu:main"}])
    return {"inline_keyboard": keyboard}


def load_command_registry() -> Dict[str, Dict[str, Any]]:
    """Loads command specifications from scripts/chatops_commands.yaml."""
    if not COMMANDS_FILE.exists():
        return {}
    try:
        with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            cmds = data.get("commands", [])
            return {c["id"]: c for c in cmds if "id" in c}
    except Exception as e:
        print(f"[ChatOps Config Error] Failed to load {COMMANDS_FILE}: {e}", flush=True)
        return {}


async def probe_rag_state() -> str:
    """Probes RAG pipeline service health, vector store, and graph database metrics."""
    lines = ["📄 *TIẾN ĐỘ & TRẠNG THÁI RAG PIPELINE* 📄\n"]
    client = get_http_client()

    # 1. Health & Database Connectivity
    is_service_reachable = False
    try:
        res = await client.get(f"{RAG_SERVICE_URL}/health", timeout=5.0)
        if res.status_code in [200, 503]:
            is_service_reachable = True
            data = res.json()
            st_text = "🟢 Khả dụng" if data.get("status") == "ok" else "🟡 Hoạt động giảm tải (Degraded)"
            lines.append(f"• Dịch vụ `rag-service`: {st_text} ({RAG_SERVICE_URL})")
            ver_raw = str(data.get("version", "2.0.0"))
            ver_str = ver_raw if ver_raw.startswith("v") else f"v{ver_raw}"
            lines.append(f"• Phiên bản: `{ver_str}`")
            checks = data.get("checks", {})
            for db_name, db_st in checks.items():
                st_icon = "🟢" if db_st in ("ok", "reconnected") else "🔴"
                lines.append(f"  └─ `{db_name}`: {st_icon} {db_st}")
        else:
            lines.append(f"• Dịch vụ `rag-service`: ⚠️ Phản hồi HTTP {res.status_code}")
    except Exception as e:
        lines.append(f"• Dịch vụ `rag-service`: 🔴 Không thể kết nối ({e})")

    # 2. Vector & Graph Stats
    if is_service_reachable:
        try:
            res_stats = await client.get(f"{RAG_SERVICE_URL}/stats", timeout=5.0)
            if res_stats.status_code == 200:
                stats = res_stats.json()
                neo4j_docs = stats.get("neo4j_docs", 0)
                neo4j_rels = stats.get("neo4j_rels", 0)
                milvus_entities = stats.get("milvus_entities", 0)
                total_target = stats.get("total_target", RAG_TARGET_DOCS)
                pct = (neo4j_docs / total_target * 100) if total_target > 0 else 0.0

                lines.append("\n📊 *SỐ LIỆU CHỈ MỤC & CƠ SỞ DỮ LIỆU:*")
                lines.append(f"• Tài liệu pháp lý (Neo4j): `{neo4j_docs}/{total_target}` ({pct:.1f}%)")
                lines.append(f"• Quan hệ pháp lý (Neo4j): `{neo4j_rels:,}` liên kết")
                lines.append(f"• Thực thể vector (Milvus): `{milvus_entities:,}` chunks")
            else:
                lines.append(f"\n• Thống kê cơ sở dữ liệu: ⚠️ HTTP {res_stats.status_code}")
        except Exception as e:
            lines.append(f"\n• Thống kê cơ sở dữ liệu: ⚠️ Lỗi truy vấn stats ({e})")
    else:
        lines.append("\n• Thống kê cơ sở dữ liệu: ⚠️ Bỏ qua do `rag-service` không khả dụng")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


async def probe_autotuner_status() -> str:
    """Probes CCBA Nightly Auto-Tuner status via Hub Monorepo CLI."""
    lines = []
    hub_dir = os.environ.get("CCBA_HUB_PATH", str(Path.home() / "ccba/ccba-agent-platform"))
    hub_python = os.path.join(hub_dir, ".venv/bin/python")
    if not os.path.exists(hub_python):
        hub_python = sys.executable
    hub_script = os.path.join(hub_dir, "scripts/eval/check_nightly_status.py")

    if not os.path.exists(hub_script):
        return f"❌ *Lỗi Cấu Hình:* Không tìm thấy script `{hub_script}`!"

    def _clean_md(val: Any) -> str:
        if val is None:
            return "N/A"
        return str(val).replace("`", "'")

    try:
        proc = await asyncio.create_subprocess_exec(
            hub_python,
            hub_script,
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=hub_dir,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=8.0)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return "❌ *Lỗi Timeout:* Lệnh kiểm tra Auto-Tuner vượt quá thời gian phản hồi (8s)!"
        except asyncio.CancelledError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            raise

        exit_code = proc.returncode or 0
        stdout_text = (stdout_bytes or b"").decode("utf-8", errors="replace").strip()
        stderr_text = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()

        if exit_code != 0:
            if "Không tìm thấy daemon" in stdout_text or "Không tìm thấy daemon" in stderr_text:
                lines.append("🌙 *CCBA NIGHTLY AUTO-TUNER* 🌙\n")
                lines.append("• *Trạng thái:* ⏸️ Đang nghỉ")
                lines.append("• _Không tìm thấy tiến trình Auto-Tuner đang chạy và chưa có báo cáo lưu trữ._")
                lines.append("• _Ca tối ưu tự động sẽ kích hoạt theo lịch ban đêm._")
            else:
                err_raw = stderr_text or stdout_text or f"Exit code {exit_code}"
                clean_err = _clean_md(err_raw[:200])
                lines.append("🌙 *CCBA NIGHTLY AUTO-TUNER* 🌙\n")
                lines.append(f"❌ *Lỗi kiểm tra Auto-Tuner:* `{clean_err}`")
            lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
            return "\n".join(lines)

        data = None
        try:
            data = json.loads(stdout_text)
        except json.JSONDecodeError:
            m = re.search(r"(\{.*\})", stdout_text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                except Exception:
                    data = None

        if not isinstance(data, dict):
            lines.append("🌙 *CCBA NIGHTLY AUTO-TUNER* 🌙\n")
            lines.append("⚠️ *Lỗi phân tích JSON:* Không thể đọc dữ liệu phản hồi.")
            lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
            return "\n".join(lines)

        mode = data.get("mode")
        is_running = bool(data.get("is_running", False))

        if mode == "live" or is_running:
            lines.append("🌙 *TIẾN ĐỘ CCBA NIGHTLY AUTO-TUNER* 🌙\n")
            pid = _clean_md(data.get("pid"))
            uptime = _clean_md(data.get("uptime"))
            lines.append(f"• *Trạng thái:* 🟢 Đang chạy (PID: `{pid}`)")
            lines.append(f"• *Thời gian chạy (Uptime):* `{uptime}`")

            cur_skill = _clean_md(data.get("current_skill"))
            completed = data.get("completed") or 0
            total = data.get("total") or 0
            pct = (completed / total * 100.0) if total > 0 else 0.0
            lines.append(f"• *Kỹ năng đang xử lý:* `{cur_skill}` (`{completed}/{total}` ~ `{pct:.1f}%`)")

            commits = data.get("commits_count") or data.get("commit_count") or 0
            lines.append(f"• *Số commits đã tạo:* `{commits}` commits")

            matrix_warn = bool(data.get("matrix_warning", False))
            if matrix_warn:
                lines.append("• *Ma trận truy vết:* 🚨 Cảnh báo lệch đồng bộ (Traceability Matrix)!")
            else:
                lines.append("• *Ma trận truy vết:* 🟢 Bình thường")
        else:
            # Post-run / Archive mode
            lines.append("🌙 *CCBA NIGHTLY AUTO-TUNER (LƯU TRỮ)* 🌙\n")
            lines.append("• *Trạng thái:* ⏸️ Đang nghỉ (Không có tiến trình đang chạy)")
            rep_file = _clean_md(data.get("report_file"))
            ts = _clean_md(data.get("timestamp"))
            branch = _clean_md(data.get("git_branch"))
            lines.append(f"• *Báo cáo gần nhất:* `{rep_file}`")
            lines.append(f"• *Phiên thực thi:* `{ts}`")
            lines.append(f"• *Nhánh Git:* `{branch}`")

            scanned = data.get("total_scanned") or data.get("total") or 0
            improved = data.get("improved_count") or data.get("completed") or 0
            commits = data.get("commit_count") or data.get("commits_count") or 0
            tok = _clean_md(data.get("total_tokens"))
            lines.append(f"• *Thống kê:* `{improved}/{scanned}` kỹ năng cải thiện | `{commits}` commits | `{tok}` tokens")

            improvements = data.get("improvements", [])
            if isinstance(improvements, list) and improvements:
                lines.append("\n🏆 *KỸ NĂNG CẢI THIỆN NỔI BẬT:*")
                for imp in improvements[:4]:
                    if isinstance(imp, dict):
                        s_name = _clean_md(imp.get("skill"))
                        s_init = _clean_md(imp.get("init"))
                        s_final = _clean_md(imp.get("final"))
                        s_delta = _clean_md(imp.get("delta"))
                        lines.append(f"• `{s_name}`: `{s_init}` ➔ `{s_final}` (`{s_delta}`)")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        clean_e = _clean_md(e)
        lines.append(f"❌ *Lỗi không mong muốn khi kiểm tra Auto-Tuner:* `{clean_e}`")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


def is_newer_version(latest: str, current: str) -> bool:
    """Returns True if latest version is strictly newer than current version."""
    if not latest or not current or latest == "unknown" or current == "unknown":
        return False
    try:
        from packaging import version as pkg_version
        return pkg_version.parse(latest) > pkg_version.parse(current)
    except Exception:
        p_latest = tuple(map(int, re.findall(r"\d+", latest)))
        p_current = tuple(map(int, re.findall(r"\d+", current)))
        return p_latest > p_current


async def check_openwebui_versions() -> Dict[str, Any]:
    """Checks current local running Open WebUI version and upstream GitHub release."""
    client = get_http_client()
    cur_ver = "unknown"
    latest_ver = "unknown"
    pub_date = ""
    html_url = "https://github.com/open-webui/open-webui/releases"

    # 1. Query local instance on host port
    try:
        res = await client.get(f"{OPENWEBUI_URL}/api/version", timeout=4.0)
        if res.status_code == 200:
            cur_ver = str(res.json().get("version", "")).lstrip("v").strip()
    except Exception as e:
        print(f"[Version Check] Failed to query local Open WebUI: {e}", flush=True)

    # 2. Query GitHub latest release
    try:
        gh_res = await client.get(
            "https://api.github.com/repos/open-webui/open-webui/releases/latest",
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "DGX-Spark-ChatOps"},
            timeout=8.0,
        )
        if gh_res.status_code == 200:
            rel = gh_res.json()
            latest_ver = str(rel.get("tag_name", "")).lstrip("v").strip()
            pub_date = str(rel.get("published_at", ""))[:10]
            html_url = str(rel.get("html_url", html_url))
    except Exception as e:
        print(f"[Version Check] Failed to query GitHub releases: {e}", flush=True)

    has_update = is_newer_version(latest_ver, cur_ver)
    return {
        "current_version": cur_ver,
        "latest_version": latest_ver,
        "has_update": has_update,
        "published_at": pub_date,
        "release_url": html_url,
    }


async def dispatch_command(
    command_id: str,
    params: Dict[str, Any],
    chat_id: int,
    message_id: int,
    title: str = "",
    cq_id: Optional[str] = None,
    timeout: Optional[int] = None,
) -> bool:
    """Universal dispatcher for commands defined in chatops_commands.yaml or emergency shell."""
    # Special handling for emergency shell execution
    if command_id == "system.emergency.exec":
        shell_cmd = params.get("cmd", "")
        job_id = hashlib.md5(f"exec_{time.time()}".encode()).hexdigest()[:6]
        await execute_shell_job(shell_cmd, job_id, chat_id, message_id, title or f"Khẩn cấp: {shell_cmd[:30]}", timeout=timeout or 60, use_shell=True)
        return True

    registry = load_command_registry()
    cmd_def = registry.get(command_id)

    if not cmd_def:
        if cq_id:
            await answer_callback(cq_id, "❌ Lệnh không tồn tại!", show_alert=True)
        err_text = f"❌ *[LỖI]* Lệnh `{command_id}` chưa được định nghĩa trong `chatops_commands.yaml`!"
        if not await edit_telegram_msg(chat_id, message_id, err_text, reply_markup=get_main_dashboard_markup()):
            await send_telegram_msg(chat_id, err_text, reply_markup=get_main_dashboard_markup())
        return False

    runner = cmd_def.get("runner", "internal")
    title = title or cmd_def.get("description", command_id)
    cmd_timeout = timeout or cmd_def.get("timeout_seconds", 120)
    is_heavy = cmd_def.get("is_heavy_op", False)
    service_lock_tmpl = cmd_def.get("service_lock")

    # 1. Parameter Validation
    param_rules = cmd_def.get("param_rules", {})
    for p_name, p_pattern in param_rules.items():
        p_val = str(params.get(p_name, ""))
        if not re.match(p_pattern, p_val):
            if cq_id:
                await answer_callback(cq_id, f"❌ Lỗi tham số {p_name}!", show_alert=True)
            err_msg = f"❌ *[LỖI THAM SỐ]* Giá trị `{p_val}` của tham số `{p_name}` không thỏa mãn mẫu an toàn `{p_pattern}`!"
            if not await edit_telegram_msg(chat_id, message_id, err_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, err_msg, reply_markup=get_main_dashboard_markup())
            return False

    # 2. Resolve Service Lock Name
    svc_lock_name = None
    if service_lock_tmpl:
        try:
            svc_lock_name = service_lock_tmpl.format(**params)
        except KeyError:
            svc_lock_name = service_lock_tmpl

    # 3. Check Mutex Locks
    if command_id == "ccba.skill.boost" and is_kernel_runner_locked():
        if cq_id:
            await answer_callback(cq_id, "⚠️ Hệ thống đang bận chạy ca Nightly Auto-Tuner. Vui lòng thử lại sau!", show_alert=True)
        warn_msg = "⚠️ *Hệ thống đang bận chạy ca Nightly Auto-Tuner. Vui lòng thử lại sau!*"
        if not await edit_telegram_msg(chat_id, message_id, warn_msg, reply_markup=get_main_dashboard_markup()):
            await send_telegram_msg(chat_id, warn_msg, reply_markup=get_main_dashboard_markup())
        return False

    if is_heavy and heavy_op_lock.locked():
        if cq_id:
            await answer_callback(cq_id, "⚠️ Đang có một tác vụ nặng khác đang chạy!", show_alert=True)
        warn_msg = "⚠️ *Đang có một tác vụ nặng khác đang chạy trên server. Vui lòng thử lại sau!*"
        if not await edit_telegram_msg(chat_id, message_id, warn_msg, reply_markup=get_main_dashboard_markup()):
            await send_telegram_msg(chat_id, warn_msg, reply_markup=get_main_dashboard_markup())
        return False

    if svc_lock_name:
        s_lock = get_service_lock(svc_lock_name)
        if s_lock.locked():
            if cq_id:
                await answer_callback(cq_id, f"⚠️ Dịch vụ {svc_lock_name} đang bận!", show_alert=True)
            busy_msg = f"⚠️ *Dịch vụ `{svc_lock_name}` đang có tác vụ khác thực thi. Vui lòng thử lại sau!*"
            if not await edit_telegram_msg(chat_id, message_id, busy_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, busy_msg, reply_markup=get_main_dashboard_markup())
            return False

    # 4. Executor implementation
    async def _execute_action() -> bool:
        nonlocal cq_id
        if runner == "internal":
            if cq_id:
                await answer_callback(cq_id)
                cq_id = None
            if command_id == "system.status":
                text = await probe_hardware_and_containers()
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, text, reply_markup=get_main_dashboard_markup())
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS", 0, 0, "Probed system status")
            elif command_id == "system.memory":
                text = await probe_memory_and_swap()
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, text, reply_markup=get_main_dashboard_markup())
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS", 0, 0, "Probed memory and swap")
            elif command_id == "system.stats":
                text = await probe_gateway_stats()
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, text, reply_markup=get_main_dashboard_markup())
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS", 0, 0, "Probed gateway stats")
            elif command_id == "host.gpu":
                text = await probe_blackwell_gpu()
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, text, reply_markup=get_main_dashboard_markup())
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS", 0, 0, "Probed GPU")
            elif command_id == "rag.ingestion.state":
                text = await probe_rag_state()
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, text, reply_markup=get_main_dashboard_markup())
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS", 0, 0, "Probed RAG state")
            elif command_id == "ccba.autotuner.status":
                text = await probe_autotuner_status()
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, text, reply_markup=get_main_dashboard_markup())
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS", 0, 0, "Probed autotuner status")
            elif command_id in ["antigravity.status", "antigravity"]:
                text = await probe_antigravity_status()
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, text, reply_markup=get_main_dashboard_markup())
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS", 0, 0, "Probed Antigravity pool status")
            elif command_id == "antigravity.account.reenable":
                acc_id = params.get("account_id", "")
                return await reenable_antigravity_account(acc_id, chat_id, message_id, cq_id=cq_id, user_id=ADMIN_USER_ID)
            elif command_id == "grok.model.menu":
                text = format_grok_menu_text()
                info = read_grok_model_info()
                markup = get_grok_menu_markup(info.get("default", ""))
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=markup):
                    await send_telegram_msg(chat_id, text, reply_markup=markup)
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS", 0, 0, "Probed grok model menu")
            elif command_id == "grok.model.set":
                new_m = params.get("model", "")
                success = update_grok_model(new_m)
                info = read_grok_model_info()
                markup = get_grok_menu_markup(info.get("default", ""))
                if success:
                    text = f"✅ *Đã chuyển model mặc định của Grok CLI sang:* `{new_m}`\n\n" + format_grok_menu_text()
                else:
                    text = f"❌ *Không thể cập nhật cấu hình sang model:* `{new_m}`\n\n" + format_grok_menu_text()
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=markup):
                    await send_telegram_msg(chat_id, text, reply_markup=markup)
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS" if success else "FAILED", 0, 0, f"Set grok model to {new_m}")
            else:
                unhandled = f"⚠️ Chưa xử lý runner internal cho lệnh `{command_id}`"
                if not await edit_telegram_msg(chat_id, message_id, unhandled, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, unhandled, reply_markup=get_main_dashboard_markup())
            return True
        elif runner in ["docker_cli", "host_script"]:
            target_tmpl = cmd_def.get("target", "")
            # Auto-inject environment context variables into execution params
            exec_params = dict(params)
            exec_params.setdefault(
                "hub_path",
                os.environ.get("CCBA_HUB_PATH", str(Path.home() / "ccba/ccba-agent-platform")),
            )
            exec_params.setdefault("project_root", str(PROJECT_ROOT))
            try:
                rendered_cmd = target_tmpl.format(**exec_params)
            except KeyError as ke:
                err_text = f"❌ *[LỖI CẤU HÌNH]* Thiếu tham số `{ke}` cho lệnh `{command_id}`!"
                if not await edit_telegram_msg(chat_id, message_id, err_text):
                    await send_telegram_msg(chat_id, err_text)
                return False

            job_id = hashlib.md5(f"{command_id}_{time.time()}".encode()).hexdigest()[:6]
            await execute_shell_job(rendered_cmd, job_id, chat_id, message_id, title, timeout=cmd_timeout)
            return True
        else:
            invalid_runner = f"❌ *[LỖI]* Runner `{runner}` không hợp lệ!"
            if not await edit_telegram_msg(chat_id, message_id, invalid_runner):
                await send_telegram_msg(chat_id, invalid_runner)
            return False

    # 5. Run with proper locks
    if is_heavy and svc_lock_name:
        async with heavy_op_lock:
            async with get_service_lock(svc_lock_name):
                return await _execute_action()
    elif is_heavy:
        async with heavy_op_lock:
            return await _execute_action()
    elif svc_lock_name:
        async with get_service_lock(svc_lock_name):
            return await _execute_action()
    else:
        return await _execute_action()


# --- 8. TELEGRAM LONG POLLER ENGINE ---
async def _handle_menu_navigation(data: str, cq_id: str, chat_id: int, message_id: int) -> bool:
    """Handles static and submenu navigation callbacks. Returns True if handled."""
    if data == "menu:main":
        await answer_callback(cq_id)
        main_menu_text = "🖥️ *BẢNG ĐIỀU KHIỂN DGX SPARK CHATOPS*\nVui lòng chọn tác vụ bên dưới:"
        await edit_telegram_msg(chat_id, message_id, main_menu_text, reply_markup=get_main_dashboard_markup())
        return True
    elif data == "menu:status":
        await dispatch_command("system.status", {}, chat_id, message_id, cq_id=cq_id)
        return True
    elif data == "menu:memory":
        await dispatch_command("system.memory", {}, chat_id, message_id, cq_id=cq_id)
        return True
    elif data == "menu:stats":
        await dispatch_command("system.stats", {}, chat_id, message_id, cq_id=cq_id)
        return True
    elif data == "menu:gpu":
        await dispatch_command("host.gpu", {}, chat_id, message_id, cq_id=cq_id)
        return True
    elif data == "menu:rag_state":
        await dispatch_command("rag.ingestion.state", {}, chat_id, message_id, cq_id=cq_id)
        return True
    elif data == "menu:antigravity":
        await dispatch_command("antigravity.status", {}, chat_id, message_id, cq_id=cq_id)
        return True
    elif data == "menu:deps_menu":
        await answer_callback(cq_id)
        deps_text = (
            "📦 *QUẢN LÝ PHỤ THUỘC (DEPENDENCY LIFECYCLE)* 📦\n\n"
            "Vui lòng chọn tác vụ kiểm tra hoặc nâng cấp bên dưới:\n"
            "• *Rà soát:* Quét phiên bản lỗi thời & CVE bảo mật trên toàn hệ thống.\n"
            "• *Tier 1 (Patch):* Nâng cấp bản vá an toàn 1-Click (0 CVE, regression check).\n"
            "• *Tier 2 (Minor):* Nâng cấp tính năng mới có khóa bundle budget & typecheck."
        )
        if not await edit_telegram_msg(chat_id, message_id, deps_text, reply_markup=get_deps_menu_markup()):
            await send_telegram_msg(chat_id, deps_text, reply_markup=get_deps_menu_markup())
        return True
    elif data == "menu:deps_check":
        await answer_callback(cq_id, "🔍 Đang rà soát phụ thuộc...")
        await dispatch_command("system.deps.check", {}, chat_id, message_id, title="Rà soát phụ thuộc & bảo mật", cq_id=None)
        return True
    elif data == "menu:deps_upg_patch":
        await answer_callback(cq_id)
        nonce = hashlib.sha256(f"deps_upg_patch_{time.time()}".encode()).hexdigest()[:8]
        action_cache[nonce] = {
            "command": "system.deps.upgrade",
            "params": {"tier": "patch"},
            "title": "Nâng cấp phụ thuộc Tier 1 (Patch)",
            "timeout": 300,
            "expires": time.time() + 60,
        }
        markup = {
            "inline_keyboard": [
                [{"text": "⚡ XÁC NHẬN NÂNG CẤP TIER 1 (PATCH)", "callback_data": f"act:{nonce}"}],
                [{"text": "🔙 Quay Lại Menu Phụ Thuộc", "callback_data": "menu:deps_menu"}],
            ]
        }
        confirm_text = (
            "⚠️ *XÁC NHẬN NÂNG CẤP PHỤ THUỘC TIER 1 (PATCH)*\n\n"
            "Thao tác này sẽ tự động cập nhật các bản vá lỗi bảo mật (Fast-track) "
            "và chạy cổng kiểm định ADR-0058 Hard Completion Lock.\n\n"
            "Bạn có muốn tiếp tục?"
        )
        if not await edit_telegram_msg(chat_id, message_id, confirm_text, reply_markup=markup):
            await send_telegram_msg(chat_id, confirm_text, reply_markup=markup)
        return True
    elif data == "menu:deps_upg_minor":
        await answer_callback(cq_id)
        nonce = hashlib.sha256(f"deps_upg_minor_{time.time()}".encode()).hexdigest()[:8]
        action_cache[nonce] = {
            "command": "system.deps.upgrade",
            "params": {"tier": "minor"},
            "title": "Nâng cấp phụ thuộc Tier 2 (Minor)",
            "timeout": 300,
            "expires": time.time() + 60,
        }
        markup = {
            "inline_keyboard": [
                [{"text": "🚀 XÁC NHẬN NÂNG CẤP TIER 2 (MINOR)", "callback_data": f"act:{nonce}"}],
                [{"text": "🔙 Quay Lại Menu Phụ Thuộc", "callback_data": "menu:deps_menu"}],
            ]
        }
        confirm_text = (
            "⚠️ *XÁC NHẬN NÂNG CẤP PHỤ THUỘC TIER 2 (MINOR)*\n\n"
            "Thao tác này sẽ nâng cấp các phiên bản Minor tương thích SemVer, "
            "tái biên dịch lockfile bằng uv và kiểm tra nghiêm ngặt ngưỡng Frontend Bundle Budget (`RULE-2.7`).\n\n"
            "Bạn có muốn tiếp tục?"
        )
        if not await edit_telegram_msg(chat_id, message_id, confirm_text, reply_markup=markup):
            await send_telegram_msg(chat_id, confirm_text, reply_markup=markup)
        return True
    elif data == "menu:autotuner":
        await dispatch_command("ccba.autotuner.status", {}, chat_id, message_id, cq_id=cq_id)
        return True
    elif data == "menu:boost_list":
        if is_kernel_runner_locked():
            await answer_callback(cq_id, "⚠️ Hệ thống đang bận chạy ca Nightly Auto-Tuner. Vui lòng thử lại sau!", show_alert=True)
            return True
        await answer_callback(cq_id)
        boost_markup = get_boost_skills_markup()
        boost_text = "⚡ *CHỌN KỸ NĂNG CẦN CAN THIỆP /BOOST:*\n_(Danh sách kỹ năng đang plateau theo thứ tự cập nhật)_"
        if not await edit_telegram_msg(chat_id, message_id, boost_text, reply_markup=boost_markup):
            await send_telegram_msg(chat_id, boost_text, reply_markup=boost_markup)
        return True
    elif data == "menu:restart_list":
        await answer_callback(cq_id)
        await edit_telegram_msg(chat_id, message_id, "🔄 *CHỌN SERVICE CẦN KHỞI ĐỘNG LẠI:*", reply_markup=get_restart_service_markup())
        return True
    elif data == "menu:upgrade_owu":
        await answer_callback(cq_id, "Đang kiểm tra phiên bản...")
        await edit_telegram_msg(
            chat_id,
            message_id,
            "⏳ *Đang kiểm tra phiên bản Open WebUI trên server và GitHub...*\nVui lòng đợi trong giây lát...",
        )
        info = await check_openwebui_versions()
        cur_ver = info["current_version"]
        latest_ver = info["latest_version"]
        has_update = info["has_update"]

        if has_update:
            prompt = (
                f"🚀 *PHÁT HIỆN BẢN CẬP NHẬT MỚI CHO OPEN WEBUI!*\n\n"
                f"• Phiên bản đang chạy: `v{cur_ver}`\n"
                f"• Phiên bản mới nhất: `v{latest_ver}` ({info['published_at']})\n"
                f"• Xem chi tiết: [GitHub Release Notes]({info['release_url']})\n\n"
                f"💡 *Kế hoạch nâng cấp:*\n"
                f"• Lệnh sẽ chạy: `bash scripts/update-openwebui.sh v{latest_ver}`\n"
                f"• Tự động sao lưu database SQLite (Zero Data Loss).\n"
                f"• Tự động rollback nếu container mới khởi động lỗi.\n"
                f"• Thời gian gián đoạn dự kiến: ~30s.\n\n"
                f"Bạn có chắc chắn muốn thực thi nâng cấp ngay bây giờ?"
            )
            nonce = hashlib.sha256(f"upg_owu_{time.time()}_{latest_ver}".encode()).hexdigest()[:8]
            action_cache[nonce] = {
                "command": "system.openwebui.upgrade",
                "params": {"target_version": f"v{latest_ver}"},
                "title": f"Nâng cấp Open WebUI lên v{latest_ver}",
                "timeout": 300,
                "expires": time.time() + 60,
            }
            markup = {
                "inline_keyboard": [
                    [{"text": f"🚀 XÁC NHẬN NÂNG CẤP (v{latest_ver})", "callback_data": f"act:{nonce}"}],
                    [{"text": "🔙 Quay Lại Menu Chính", "callback_data": "menu:main"}],
                ]
            }
            await edit_telegram_msg(chat_id, message_id, prompt, reply_markup=markup)
        elif cur_ver != "unknown":
            up_to_date_msg = (
                f"✅ *OPEN WEBUI ĐÃ Ở PHIÊN BẢN MỚI NHẤT!*\n\n"
                f"• Phiên bản đang chạy: `v{cur_ver}`\n"
                f"• Phiên bản trên GitHub: `v{latest_ver}`\n"
                f"• Trạng thái: Hệ thống đang vận hành phiên bản mới nhất, không cần cập nhật."
            )
            reinstall_nonce = hashlib.sha256(f"reinstall_owu_{time.time()}".encode()).hexdigest()[:8]
            action_cache[reinstall_nonce] = {
                "command": "system.openwebui.upgrade",
                "params": {"target_version": f"v{cur_ver}"},
                "title": f"Cài đặt lại Open WebUI v{cur_ver}",
                "timeout": 300,
                "expires": time.time() + 60,
            }
            markup = {
                "inline_keyboard": [
                    [{"text": f"🔄 Cài Đặt Lại v{cur_ver} (Reinstall)", "callback_data": f"act:{reinstall_nonce}"}],
                    [{"text": "🔙 Quay Lại Menu Chính", "callback_data": "menu:main"}],
                ]
            }
            await edit_telegram_msg(chat_id, message_id, up_to_date_msg, reply_markup=markup)
        else:
            err_msg = (
                f"⚠️ *KHÔNG THỂ KIỂM TRA PHIÊN BẢN TỰ ĐỘNG*\n\n"
                f"• Phiên bản local: `{cur_ver}`\n"
                f"• Phiên bản GitHub: `{latest_ver}`\n\n"
                f"Bạn có thể chỉ định phiên bản nâng cấp thủ công bằng lệnh:\n"
                f"`/upgrade_owu <version>` (ví dụ: `/upgrade_owu v0.11.4`)"
            )
            await edit_telegram_msg(chat_id, message_id, err_msg, reply_markup=get_main_dashboard_markup())
        return True
    elif data == "menu:grok_menu":
        await answer_callback(cq_id)
        info = read_grok_model_info()
        grok_text = format_grok_menu_text()
        markup = get_grok_menu_markup(info.get("default", ""))
        if not await edit_telegram_msg(chat_id, message_id, grok_text, reply_markup=markup):
            await send_telegram_msg(chat_id, grok_text, reply_markup=markup)
        return True
    elif data == "menu:grok_effort_menu":
        await answer_callback(cq_id)
        effort_text = format_grok_effort_text()
        info = read_grok_model_info()
        markup = get_grok_effort_markup(info.get("effort", ""))
        if not await edit_telegram_msg(chat_id, message_id, effort_text, reply_markup=markup):
            await send_telegram_msg(chat_id, effort_text, reply_markup=markup)
        return True
    elif data == "menu:help":
        await answer_callback(cq_id)
        await edit_telegram_msg(chat_id, message_id, HELP_TEXT, reply_markup=get_main_dashboard_markup())
        return True

    return False


async def _handle_callback_query(cq: Dict[str, Any], update: Dict[str, Any]) -> None:
    """Handles callback queries from inline keyboard button clicks."""
    cq_id = cq["id"]
    from_user = cq.get("from", {})
    user_id = from_user.get("id")
    msg = cq.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")
    data = cq.get("data", "")

    # Strict ACL
    if user_id != ADMIN_USER_ID:
        await answer_callback(cq_id, "❌ Không có quyền truy cập!", show_alert=True)
        append_audit_log("callback", data, {"user_id": user_id}, user_id, "FORBIDDEN", 0, -1, "Unknown user tried to click button")
        return

    # 1. Main Navigation Menu callbacks
    if await _handle_menu_navigation(data, cq_id, chat_id, message_id):
        return

    # 2. Dynamic Action Buttons (act:<nonce> or act:antigravity_reenable:<account_id>)
    if data.startswith("bst:"):
        skill = data.split(":", 1)[1].strip()
        if not skill or not re.match(r"^[a-zA-Z0-9_-]+$", skill):
            await answer_callback(cq_id, "❌ Tên kỹ năng không hợp lệ!", show_alert=True)
            return
        if is_kernel_runner_locked():
            await answer_callback(cq_id, "⚠️ Hệ thống đang bận chạy ca Nightly Auto-Tuner. Vui lòng thử lại sau!", show_alert=True)
            return
        await answer_callback(cq_id)
        nonce = hashlib.sha256(f"bst_{time.time()}_{skill}".encode()).hexdigest()[:8]
        action_cache[nonce] = {
            "command": "ccba.skill.boost",
            "params": {"skill": skill},
            "title": f"🚀 /boost {skill}",
            "timeout": 600,
            "expires": time.time() + 60,
        }
        confirm_msg = (
            f"⚡ *XÁC NHẬN CAN THIỆP SUY LUẬN SÂU (/BOOST)* ⚡\n\n"
            f"• Kỹ năng mục tiêu: `{skill}`\n"
            f"• Thời hạn xác nhận: 60 giây\n\n"
            f"Bạn có chắc chắn muốn khởi chạy `/boost {skill}` ngay bây giờ?"
        )
        markup = {
            "inline_keyboard": [
                [{"text": "✅ Xác Nhận Chạy /boost", "callback_data": f"act:{nonce}"}],
                [{"text": "❌ Hủy Bỏ", "callback_data": "menu:main"}],
            ]
        }
        if not await edit_telegram_msg(chat_id, message_id, confirm_msg, reply_markup=markup):
            await send_telegram_msg(chat_id, confirm_msg, reply_markup=markup)
        return
    elif data.startswith("rst:"):
        svc = data.split(":", 1)[1]
        await dispatch_command("system.container.restart", {"service": svc}, chat_id, message_id, title=f"Khởi động lại {svc}", cq_id=cq_id)
        return
    elif data.startswith("grok_set:"):
        target_model = data.split("grok_set:", 1)[1].strip()
        allowed = [m[0] for m in GROK_AVAILABLE_MODELS]
        if target_model not in allowed:
            await answer_callback(cq_id, f"❌ Model {target_model} không hợp lệ!", show_alert=True)
            return
        success = update_grok_model(target_model)
        if success:
            await answer_callback(cq_id, f"✅ Đã đổi sang {target_model}!")
            append_audit_log("callback", data, {"model": target_model}, user_id, "SUCCESS", 0, 0, f"Switched Grok model to {target_model}")
        else:
            await answer_callback(cq_id, "❌ Cập nhật config thất bại!", show_alert=True)
            append_audit_log("callback", data, {"model": target_model}, user_id, "FAILED", 0, -1, "Failed to update Grok model config")
        info = read_grok_model_info()
        grok_text = format_grok_menu_text()
        markup = get_grok_menu_markup(info.get("default", ""))
        if not await edit_telegram_msg(chat_id, message_id, grok_text, reply_markup=markup):
            await send_telegram_msg(chat_id, grok_text, reply_markup=markup)
        return
    elif data.startswith("grok_effort:"):
        target_effort = data.split("grok_effort:", 1)[1].strip()
        allowed_efforts = [e[0] for e in GROK_EFFORT_LEVELS]
        if target_effort not in allowed_efforts:
            await answer_callback(cq_id, f"❌ Effort {target_effort} không hợp lệ!", show_alert=True)
            return
        success = update_grok_effort(target_effort)
        if success:
            await answer_callback(cq_id, f"🎯 Mức suy luận: {target_effort}!")
            append_audit_log("callback", data, {"effort": target_effort}, user_id, "SUCCESS", 0, 0, f"Switched Grok reasoning effort to {target_effort}")
        else:
            await answer_callback(cq_id, "❌ Cập nhật config thất bại!", show_alert=True)
            append_audit_log("callback", data, {"effort": target_effort}, user_id, "FAILED", 0, -1, "Failed to update Grok effort config")
        effort_text = format_grok_effort_text()
        markup = get_grok_effort_markup(target_effort)
        if not await edit_telegram_msg(chat_id, message_id, effort_text, reply_markup=markup):
            await send_telegram_msg(chat_id, effort_text, reply_markup=markup)
        return
    elif data.startswith("act:antigravity_reenable:"):
        account_id = data.split("act:antigravity_reenable:", 1)[1].strip()
        if not account_id or not re.match(r"^[a-zA-Z0-9_.@-]+$", account_id):
            await answer_callback(cq_id, "❌ ID tài khoản không hợp lệ!", show_alert=True)
            return
        await answer_callback(cq_id, f"🔍 Đang kiểm tra probe {account_id}...")
        status_msg_id = await send_telegram_msg(chat_id, f"⏳ *[HEALTH PROBE GATE]* Đang kiểm tra tài khoản `{account_id}`...\nVui lòng đợi...")
        await reenable_antigravity_account(account_id, chat_id, status_msg_id or message_id, cq_id=None, user_id=user_id)
        return
    elif data.startswith("act:"):
        nonce = data.split(":", 1)[1]
        entry = action_cache.pop(nonce, None)
        if not entry or time.time() > entry.get("expires", 0):
            await answer_callback(cq_id, "⚠️ Thao tác đã hết hạn hoặc đã được thực thi!", show_alert=True)
            return

        cmd = entry["command"]
        params = entry.get("params", {})
        title = entry.get("title", "")
        timeout = entry.get("timeout")

        if cmd == "ccba.skill.boost" and is_kernel_runner_locked():
            action_cache[nonce] = entry
            await answer_callback(cq_id, "⚠️ Hệ thống đang bận chạy ca Nightly Auto-Tuner. Vui lòng thử lại sau!", show_alert=True)
            return

        await answer_callback(cq_id, f"🚀 Khởi chạy {title}...")
        status_msg_id = await send_telegram_msg(chat_id, f"⏳ *[ĐANG CHẠY]* `{title}`\nVui lòng đợi...")
        dispatched = await dispatch_command(cmd, params, chat_id, status_msg_id or message_id, title=title, cq_id=None, timeout=timeout)
        if not dispatched:
            action_cache[nonce] = entry
        return

    # Fallback for unhandled or expired callback query to prevent hanging spinner in Telegram
    await answer_callback(cq_id, "⚠️ Tác vụ đã hết hạn hoặc không khả dụng!")
    return


async def _handle_text_message(msg: Dict[str, Any]) -> None:
    """Handles incoming text messages and slash commands."""
    chat_id = msg.get("chat", {}).get("id")
    user_id = msg.get("from", {}).get("id")
    message_id = msg.get("message_id")
    text = msg.get("text", "").strip()

    # Anti-Replay Protection for Stale Telegram Updates
    msg_date = msg.get("date", 0)
    if msg_date and (time.time() - msg_date > 120):
        age_sec = int(time.time() - msg_date)
        print(f"[Anti-Replay] Dropping stale update/message {message_id} (age: {age_sec}s > 120s)", flush=True)
        append_audit_log(
            trigger_type="message",
            command=text,
            params={"message_id": message_id, "msg_date": msg_date, "age_seconds": age_sec},
            user_id=user_id or 0,
            status="STALE_DROPPED",
            duration_ms=0,
            exit_code=-1,
            details=f"Stale update dropped by anti-replay protection (age: {age_sec}s > 120s)",
        )
        return

    # Strict ACL
    if user_id != ADMIN_USER_ID:
        append_audit_log("message", text, {"user_id": user_id}, user_id, "FORBIDDEN", 0, -1, "Unknown user message dropped")
        return

    cmd_token = text.split()[0].split("@")[0].lower() if text else ""

    # 1. /start or /menu
    if cmd_token in ["/start", "/menu"]:
        await send_telegram_msg(chat_id, "🖥️ *BẢNG ĐIỀU KHIỂN DGX SPARK CHATOPS*\nVui lòng chọn tác vụ bên dưới:", reply_markup=get_main_dashboard_markup())
        return

    # 2. /status
    if cmd_token == "/status":
        sent_id = await send_telegram_msg(chat_id, "⏳ Đang kiểm tra trạng thái...")
        if sent_id:
            await dispatch_command("system.status", {}, chat_id, sent_id)
        return

    # 2a. /memory
    if cmd_token == "/memory":
        sent_id = await send_telegram_msg(chat_id, "⏳ Đang kiểm tra chi tiết bộ nhớ & Swap...")
        if sent_id:
            await dispatch_command("system.memory", {}, chat_id, sent_id)
        return

    # 2b. /stats
    if cmd_token == "/stats":
        sent_id = await send_telegram_msg(chat_id, "⏳ Đang truy vấn thống kê AI Gateway...")
        if sent_id:
            await dispatch_command("system.stats", {}, chat_id, sent_id)
        return

    # 3. /gpu
    if cmd_token == "/gpu":
        sent_id = await send_telegram_msg(chat_id, "⏳ Đang truy vấn GPU Blackwell...")
        if sent_id:
            await dispatch_command("host.gpu", {}, chat_id, sent_id)
        return

    # 4. /rag_state
    if cmd_token == "/rag_state":
        sent_id = await send_telegram_msg(chat_id, "⏳ Đang kiểm tra hàng đợi RAG...")
        if sent_id:
            await dispatch_command("rag.ingestion.state", {}, chat_id, sent_id)
        return

    # 4a. /autotuner
    if cmd_token == "/autotuner":
        sent_id = await send_telegram_msg(chat_id, "⏳ Đang kiểm tra trạng thái Nightly Auto-Tuner...")
        if sent_id:
            await dispatch_command("ccba.autotuner.status", {}, chat_id, sent_id)
        return

    # 4b. /antigravity
    if cmd_token in ["/antigravity", "/accounts"]:
        sent_id = await send_telegram_msg(chat_id, "⏳ Đang kiểm tra hồ bơi tài khoản Antigravity...")
        if sent_id:
            await dispatch_command("antigravity.status", {}, chat_id, sent_id)
        return

    # 4b2. /reenable_account <account_id>
    if cmd_token in ["/reenable_account", "/reenable"]:
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await send_telegram_msg(chat_id, "Cú pháp: `/reenable_account <account_id>` (Ví dụ: `/reenable_account acc_123`)")
            return
        acc_id = parts[1].strip()
        if not re.match(r"^[a-zA-Z0-9_.@-]+$", acc_id):
            await send_telegram_msg(chat_id, "❌ ID tài khoản không hợp lệ!")
            return
        sent_id = await send_telegram_msg(chat_id, f"⏳ *[HEALTH PROBE GATE]* Đang kiểm tra tài khoản `{acc_id}`...\nVui lòng đợi...")
        if sent_id:
            await reenable_antigravity_account(acc_id, chat_id, sent_id, user_id=user_id or ADMIN_USER_ID)
        return

    # 4b. /deps
    if cmd_token == "/deps":
        sent_id = await send_telegram_msg(chat_id, "⏳ Đang rà soát phụ thuộc & kiểm tra bảo mật...")
        if sent_id:
            await dispatch_command("system.deps.check", {}, chat_id, sent_id, title="Rà soát phụ thuộc & bảo mật")
        return

    # 4c. /upgrade_deps [patch|minor]
    if cmd_token == "/upgrade_deps":
        parts = text.split(maxsplit=1)
        tier = "patch"
        if len(parts) > 1:
            tier = parts[1].strip().lower()
        if tier not in ["patch", "minor"]:
            await send_telegram_msg(chat_id, "⚠️ Cú pháp: `/upgrade_deps [patch|minor]` (Mặc định: `patch`)")
            return
        sent_id = await send_telegram_msg(chat_id, f"⏳ Đang chuẩn bị nâng cấp phụ thuộc ({tier})...")
        if sent_id:
            await dispatch_command("system.deps.upgrade", {"tier": tier}, chat_id, sent_id, title=f"Nâng cấp phụ thuộc ({tier})")
        return

    # 4d. /grok or /grok_model
    if cmd_token in ["/grok", "/grok_model"]:
        info = read_grok_model_info()
        grok_text = format_grok_menu_text()
        markup = get_grok_menu_markup(info.get("default", ""))
        await send_telegram_msg(chat_id, grok_text, reply_markup=markup)
        return

    # 4e. /set_grok_model <model>
    if cmd_token in ["/set_grok_model", "/grok_set"]:
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            allowed_str = ", ".join([f"`{m[0]}`" for m in GROK_AVAILABLE_MODELS])
            await send_telegram_msg(chat_id, f"⚠️ Cú pháp: `/set_grok_model <model>`\nCác model khả dụng: {allowed_str}")
            return
        target_model = parts[1].strip()
        sent_id = await send_telegram_msg(chat_id, f"⏳ Đang chuyển model Grok CLI sang `{target_model}`...")
        if sent_id:
            await dispatch_command("grok.model.set", {"model": target_model}, chat_id, sent_id, title=f"Đổi model Grok sang {target_model}")
        return

    # 4g. /grok_effort
    if cmd_token == "/grok_effort":
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            allowed_efforts = ", ".join([f"`{e[0]}`" for e in GROK_EFFORT_LEVELS])
            await send_telegram_msg(chat_id, f"⚠️ Cú pháp: `/grok_effort <level>`\nCác mức khả dụng: {allowed_efforts}")
            return
        target_effort = parts[1].strip().lower()
        allowed_efforts = [e[0] for e in GROK_EFFORT_LEVELS]
        if target_effort not in allowed_efforts:
            await send_telegram_msg(chat_id, f"❌ Mức effort `{target_effort}` không hợp lệ!")
            return
        success = update_grok_effort(target_effort)
        if success:
            await send_telegram_msg(chat_id, f"🎯 Đã chuyển mức suy luận Grok CLI sang: `{target_effort}`\n\n" + format_grok_effort_text())
            append_audit_log("message", "/grok_effort", {"effort": target_effort}, user_id or ADMIN_USER_ID, "SUCCESS", 0, 0, f"Set grok effort to {target_effort}")
        else:
            await send_telegram_msg(chat_id, f"❌ Cập nhật cấu hình effort thất bại!\n\n" + format_grok_effort_text())
            append_audit_log("message", "/grok_effort", {"effort": target_effort}, user_id or ADMIN_USER_ID, "FAILED", 0, -1, "Failed to update Grok effort config")
        return

    # 4f. /help
    if cmd_token == "/help":
        await send_telegram_msg(chat_id, HELP_TEXT, reply_markup=get_main_dashboard_markup())
        return

    # 5. /restart <service>
    if cmd_token == "/restart":
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            registry = load_command_registry()
            restart_cmd = registry.get("system.container.restart", {})
            whitelist_pattern = restart_cmd.get("param_rules", {}).get("service", "")
            allowed = whitelist_pattern.replace("^(", "").replace(")$", "").replace("|", ", ") if whitelist_pattern else "open-webui, ..."
            await send_telegram_msg(chat_id, f"Cú pháp: `/restart <service_name>` (Ví dụ: `/restart open-webui`)\nCác dịch vụ hợp lệ: `{allowed}`")
            return
        svc = parts[1].strip()
        sent_id = await send_telegram_msg(chat_id, f"⏳ Đang chuẩn bị khởi động lại {svc}...")
        if sent_id:
            await dispatch_command("system.container.restart", {"service": svc}, chat_id, sent_id, title=f"Khởi động lại {svc}")
        return

    # 6. /upgrade_owu [version]
    if cmd_token == "/upgrade_owu":
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            ver = parts[1].strip()
            sent_id = await send_telegram_msg(chat_id, f"⏳ Đang chuẩn bị nâng cấp Open WebUI lên {ver}...")
            if sent_id:
                await dispatch_command(
                    "system.openwebui.upgrade",
                    {"target_version": ver},
                    chat_id,
                    sent_id,
                    title=f"Nâng cấp Open WebUI lên {ver}",
                )
        else:
            sent_id = await send_telegram_msg(chat_id, "⏳ Đang kiểm tra phiên bản Open WebUI trên server và GitHub...")
            info = await check_openwebui_versions()
            cur_ver = info["current_version"]
            latest_ver = info["latest_version"]
            has_update = info["has_update"]

            if has_update and sent_id:
                prompt = (
                    f"🚀 *PHÁT HIỆN BẢN CẬP NHẬT MỚI CHO OPEN WEBUI!*\n\n"
                    f"• Phiên bản đang chạy: `v{cur_ver}`\n"
                    f"• Phiên bản mới nhất: `v{latest_ver}` ({info['published_at']})\n\n"
                    f"Bạn có muốn nâng cấp lên `v{latest_ver}` ngay bây giờ?"
                )
                nonce = hashlib.sha256(f"upg_owu_{time.time()}_{latest_ver}".encode()).hexdigest()[:8]
                action_cache[nonce] = {
                    "command": "system.openwebui.upgrade",
                    "params": {"target_version": f"v{latest_ver}"},
                    "title": f"Nâng cấp Open WebUI lên v{latest_ver}",
                    "timeout": 300,
                    "expires": time.time() + 60,
                }
                markup = {
                    "inline_keyboard": [
                        [{"text": f"🚀 XÁC NHẬN NÂNG CẤP (v{latest_ver})", "callback_data": f"act:{nonce}"}],
                        [{"text": "🔙 Quay Lại Menu Chính", "callback_data": "menu:main"}],
                    ]
                }
                await edit_telegram_msg(chat_id, sent_id, prompt, reply_markup=markup)
            elif cur_ver != "unknown" and sent_id:
                await edit_telegram_msg(
                    chat_id,
                    sent_id,
                    f"✅ *Open WebUI đã ở phiên bản mới nhất (`v{cur_ver}`). Không cần nâng cấp!*\n\n"
                    f"Nếu muốn cài đặt lại bản hiện tại, gõ: `/upgrade_owu v{cur_ver}`",
                    reply_markup=get_main_dashboard_markup(),
                )
            elif sent_id:
                await edit_telegram_msg(
                    chat_id,
                    sent_id,
                    "⚠️ Không thể kiểm tra phiên bản tự động. Vui lòng chỉ định: `/upgrade_owu <version>`",
                    reply_markup=get_main_dashboard_markup(),
                )
        return

    # 7. /exec <PIN> <command>
    if cmd_token == "/exec":
        # Immediately delete message to purge PIN from history
        await delete_telegram_msg(chat_id, message_id)

        remaining_lock = check_brute_force_lockout()
        if remaining_lock:
            await send_telegram_msg(chat_id, f"🚨 *LỆNH /EXEC ĐANG BỊ KHÓA!* Vui lòng thử lại sau `{remaining_lock // 60} phút {remaining_lock % 60} giây`.")
            return

        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await send_telegram_msg(chat_id, "⚠️ Cú pháp: `/exec <PIN> <command>`")
            return

        input_pin = parts[1].strip()
        shell_cmd = parts[2].strip()

        if not CHATOPS_EMERGENCY_PIN or len(CHATOPS_EMERGENCY_PIN) < 6:
            await send_telegram_msg(chat_id, "❌ Lệnh `/exec` bị vô hiệu hóa vì CHATOPS_EMERGENCY_PIN chưa được thiết lập an toàn.")
            return

        if not hmac.compare_digest(input_pin, CHATOPS_EMERGENCY_PIN):
            attempts = register_failed_pin_attempt()
            if attempts >= 3:
                await send_telegram_msg(chat_id, "🚨 *CẢNH BÁO AN NINH:* Bạn đã nhập sai PIN 3 lần! Lệnh `/exec` bị khóa 1 giờ.")
                append_audit_log("exec", shell_cmd, {"attempts": attempts}, ADMIN_USER_ID, "LOCKED", 0, -1, "Brute force lockout triggered")
            else:
                await send_telegram_msg(chat_id, f"❌ *SAI MÃ PIN BẢO MẬT!* (Lần thử {attempts}/3)")
                append_audit_log("exec", shell_cmd, {"attempts": attempts}, ADMIN_USER_ID, "AUTH_FAILED", 0, -1, f"Failed PIN attempt ({attempts}/3)")
            return

        reset_failed_pin_attempts()

        # Check blacklist
        for bl_pattern in SHELL_BLACKLIST:
            if re.search(bl_pattern, shell_cmd, re.IGNORECASE):
                await send_telegram_msg(chat_id, f"❌ *LỆNH BỊ CHẶN BỞI BỘ LỌC AN TOÀN:* Mẫu `{bl_pattern}` không được phép thực thi!")
                append_audit_log("exec", shell_cmd, {}, ADMIN_USER_ID, "BLOCKED", 0, -1, f"Matched blacklist: {bl_pattern}")
                return

        # Two-phase confirmation
        nonce = hashlib.sha256(f"exec_{time.time()}_{shell_cmd}".encode()).hexdigest()[:8]
        action_cache[nonce] = {
            "command": "system.emergency.exec",
            "params": {"cmd": shell_cmd},
            "title": f"Lệnh khẩn cấp: {shell_cmd[:30]}",
            "expires": time.time() + 60,
            "timeout": 60,
        }
        confirm_msg = (
            f"⚠️ *XÁC NHẬN THỰC THI LỆNH KHẨN CẤP*\n\n"
            f"• Lệnh: `{shell_cmd}`\n"
            f"• Người yêu cầu: Admin ({user_id})\n"
            f"• Thời hạn xác nhận: 60 giây\n\n"
            f"Bạn có chắc chắn muốn thực thi lệnh shell này?"
        )
        markup = {
            "inline_keyboard": [
                [{"text": "✅ XÁC NHẬN THỰC THI", "callback_data": f"act:{nonce}"}],
                [{"text": "❌ HỦY BỎ", "callback_data": "menu:main"}],
            ]
        }
        await send_telegram_msg(chat_id, confirm_msg, reply_markup=markup)
        return

    # 8. /boost <skill>
    if cmd_token == "/boost":
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await send_telegram_msg(chat_id, "Cú pháp: `/boost <skill_name>` (Ví dụ: `/boost bigbim-risk`)")
            return
        skill_arg = parts[1].strip()
        if is_kernel_runner_locked():
            await send_telegram_msg(chat_id, "⚠️ *Hệ thống đang bận chạy ca Nightly Auto-Tuner. Vui lòng thử lại sau!*")
            return
        sent_id = await send_telegram_msg(chat_id, f"⏳ *[ĐANG CHẠY]* `🚀 /boost {skill_arg}`\nVui lòng đợi...")
        if sent_id:
            await dispatch_command(
                "ccba.skill.boost",
                {"skill": skill_arg},
                chat_id,
                sent_id,
                title=f"🚀 /boost {skill_arg}",
            )
        return


async def process_telegram_update(update: Dict[str, Any]) -> None:
    """Processes an incoming Telegram update with strict ACL and atomic actions."""
    if "callback_query" in update:
        await _handle_callback_query(update["callback_query"], update)
    elif "message" in update:
        await _handle_text_message(update["message"])


async def telegram_polling_loop() -> None:
    """Long Polling loop running concurrently with FastAPI."""
    offset: Optional[int] = None
    print("[Telegram Poller] Starting long polling loop...", flush=True)

    while True:
        try:
            payload: Dict[str, Any] = {"timeout": 30, "limit": 50, "allowed_updates": ["message", "callback_query"]}
            if offset is not None:
                payload["offset"] = offset

            data = await telegram_request("getUpdates", payload)
            if data and data.get("ok"):
                updates = data.get("result", [])
                if updates:
                    offset = max(u["update_id"] for u in updates) + 1
                    for u in updates:
                        try:
                            await process_telegram_update(u)
                        except Exception as ex:
                            print(f"[Update Error] {ex}", flush=True)
            else:
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            print("[Telegram Poller] Stopping loop...", flush=True)
            break
        except Exception as e:
            print(f"[Poller Exception] {e}. Backing off 5s...", flush=True)
            await asyncio.sleep(5)


def purge_expired_action_cache() -> int:
    """Purges expired nonces from action_cache to prevent memory leaks. Returns count of purged items."""
    now = time.time()
    expired_keys = [k for k, v in action_cache.items() if now > v.get("expires", 0)]
    for k in expired_keys:
        action_cache.pop(k, None)
    return len(expired_keys)


async def cleanup_action_cache_loop(interval_seconds: int = 600) -> None:
    """Periodically purges expired nonces from action_cache to prevent memory leaks."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            purged = purge_expired_action_cache()
            if purged:
                print(f"[ChatOps Cache] Purged {purged} expired action nonce(s).", flush=True)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[ChatOps Cache Warning] Error during cache cleanup: {e}", flush=True)


# --- 9. FASTAPI INTERNAL REST SERVER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Initialize persistent HTTP client
    get_http_client()

    # 1. Wait for network
    print("[ChatOps] Checking network connectivity...", flush=True)
    for _ in range(12):
        try:
            client = get_http_client()
            res = await client.get("https://api.telegram.org", timeout=4.0)
            if res.status_code in [200, 302, 404]:
                print("[ChatOps] Network and Telegram API reachable.", flush=True)
                break
        except Exception:
            await asyncio.sleep(3)

    # 2. Reset Webhook
    await telegram_request("deleteWebhook", {"drop_pending_updates": False})

    # 3. Start Background Tasks
    poller_task = asyncio.create_task(telegram_polling_loop())
    cache_cleaner_task = asyncio.create_task(cleanup_action_cache_loop())

    yield

    # 4. Graceful Shutdown
    poller_task.cancel()
    cache_cleaner_task.cancel()
    try:
        await asyncio.gather(poller_task, cache_cleaner_task, return_exceptions=True)
    except Exception:
        pass

    global http_client, client_loop
    if http_client and not http_client.is_closed:
        await http_client.aclose()
        http_client = None
        client_loop = None

    print("[ChatOps] Daemon shutdown complete.", flush=True)


app = FastAPI(title="DGX-ChatOps Universal Gateway", lifespan=lifespan)


@app.middleware("http")
async def verify_ip_and_security(request: Request, call_next):
    client_ip = request.client.host if request.client else "127.0.0.1"
    try:
        ip_obj = ipaddress.ip_address(client_ip)
        is_allowed = any(ip_obj in net for net in ALLOWED_NETWORKS)
    except ValueError:
        is_allowed = False

    if not is_allowed and request.url.path != "/health":
        return Response(content="Forbidden: Internal Network Only", status_code=403)

    return await call_next(request)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "dgx-chatops", "timestamp": time.time()}


@app.get("/api/v1/probe/{probe_type}")
async def handle_internal_probe(probe_type: str, x_chatops_secret: Optional[str] = Header(None)):
    """Executes read-only infrastructure probe and returns formatted text."""
    if not CHATOPS_INTERNAL_SECRET or not x_chatops_secret or not hmac.compare_digest(x_chatops_secret, CHATOPS_INTERNAL_SECRET):
        raise HTTPException(status_code=401, detail="Invalid ChatOps Secret Header")

    pt = probe_type.lower().strip()
    match pt:
        case "gpu":
            res = await probe_blackwell_gpu()
        case "memory" | "ram" | "swap":
            res = await probe_memory_and_swap()
        case "containers" | "hardware" | "status":
            res = await probe_hardware_and_containers()
        case "rag":
            res = await probe_rag_state()
        case "gateway":
            res = await probe_gateway_stats()
        case "antigravity":
            res = await probe_antigravity_status()
        case _:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported probe_type: '{probe_type}'. Supported: gpu, memory, containers, rag, gateway, antigravity",
            )

    return {"probe_type": pt, "result": res}


ALLOWED_NOTIFY_COMMANDS = {
    "system.container.restart",
    "system.openwebui.upgrade",
    "system.deps.check",
    "system.deps.upgrade",
    "ccba.skill.boost",
    "antigravity.account.reenable",
    "grok.model.set",
}


@app.post("/api/v1/notify")
async def handle_internal_notify(payload: Dict[str, Any], x_chatops_secret: Optional[str] = Header(None)):
    """Receives alerts from Docker containers and sends Telegram messages with interactive buttons."""
    if not CHATOPS_INTERNAL_SECRET or not x_chatops_secret or not hmac.compare_digest(x_chatops_secret, CHATOPS_INTERNAL_SECRET):
        raise HTTPException(status_code=401, detail="Invalid ChatOps Secret Header")

    title = str(payload.get("title", "Thông báo từ máy chủ DGX Spark")).strip()
    body = str(payload.get("body", "")).strip()
    severity = payload.get("severity", "INFO")
    actions = payload.get("actions", [])

    if not isinstance(actions, list):
        raise HTTPException(status_code=400, detail="Trường 'actions' phải là một danh sách")

    registry = load_command_registry()
    inline_keyboard = []

    for act in actions:
        if not isinstance(act, dict):
            continue
        cmd = str(act.get("command", "")).strip()

        # Adversarial Defense 1: Chặn tuyệt đối emergency exec
        if cmd == "system.emergency.exec" or cmd.startswith("system.emergency"):
            raise HTTPException(status_code=403, detail="Tác vụ khẩn cấp 'system.emergency.exec' bị cấm qua cơ chế notify")

        # Adversarial Defense 2: Whitelist commands
        if cmd not in ALLOWED_NOTIFY_COMMANDS:
            raise HTTPException(status_code=403, detail=f"Lệnh '{cmd}' không nằm trong danh sách được phép đề xuất (ALLOWED_NOTIFY_COMMANDS)")

        cmd_def = registry.get(cmd)
        if not cmd_def:
            raise HTTPException(status_code=400, detail=f"Lệnh '{cmd}' chưa được định nghĩa trong registry")

        # Adversarial Defense 3: Validate params với param_rules TRƯỚC KHI tạo nonce / gửi Telegram
        params = act.get("params", {})
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail="Trường 'params' phải là một dictionary")

        param_rules = cmd_def.get("param_rules", {})
        extra_keys = set(params.keys()) - set(param_rules.keys())
        if extra_keys:
            raise HTTPException(status_code=400, detail=f"Tham số không được phép cho lệnh '{cmd}': {extra_keys}")

        for p_name, p_pattern in param_rules.items():
            p_val = str(params.get(p_name, ""))
            if not re.match(p_pattern, p_val):
                raise HTTPException(status_code=400, detail=f"Tham số '{p_name}'='{p_val}' không thỏa mãn mẫu an toàn '{p_pattern}'")

        # Adversarial Defense 4: Server-side generated action labels (Chống UI spoofing)
        param_summary = ", ".join(f"{k}={v}" for k, v in params.items())
        desc = cmd_def.get("description", cmd)
        server_title = f"Thực thi: {desc}" + (f" ({param_summary})" if param_summary else "")
        server_label = f"▶️ {cmd}" + (f" ({param_summary})" if param_summary else "")
        if len(server_label) > 35:
            server_label = server_label[:32] + "..."

        nonce = hashlib.sha256(f"{cmd}_{time.time()}_{uuid.uuid4().hex[:6]}".encode()).hexdigest()[:8]
        reg_timeout = cmd_def.get("timeout_seconds", 120)
        action_cache[nonce] = {
            "command": cmd,
            "params": params,
            "title": server_title,
            "timeout": reg_timeout,
            "expires": time.time() + min(act.get("ttl_seconds", 3600), 7200),
        }
        inline_keyboard.append([{"text": server_label, "callback_data": f"act:{nonce}"}])

    if inline_keyboard:
        # Khi có actions đề xuất tác vụ: Tiêu đề và thân thẻ BẮT BUỘC sinh từ server registry (chống UI spoofing)
        action_summaries = []
        for nonce, entry in action_cache.items():
            if any(btn.get("callback_data") == f"act:{nonce}" for row in inline_keyboard for btn in row):
                cmd_id = entry["command"]
                cmd_def = registry.get(cmd_id, {})
                display_timeout = entry["timeout"] if entry["timeout"] is not None else cmd_def.get("timeout_seconds", 120)
                action_summaries.append(
                    f"• *Mã lệnh:* `{cmd_id}`\n"
                    f"  *Mô tả:* {cmd_def.get('description', cmd_id)}\n"
                    f"  *Tham số:* `{json.dumps(entry['params'], ensure_ascii=False)}`\n"
                    f"  *Giới hạn thời gian:* `{display_timeout}s`"
                )
        body_text = "\n\n".join(action_summaries)
        icon = "🔔" if severity == "INFO" else "⚠️" if severity == "WARNING" else "🚨"
        escaped_title = escape_md(title[:200])
        escaped_body = escape_md(body[:2000]) if body else ""
        client_info = f"{icon} *{escaped_title}*\n\n{escaped_body}\n\n─────────────\n\n"
        msg_text = (
            f"{client_info}"
            f"⚡ *[HÀNH ĐỘNG ĐỀ XUẤT]*\n\n"
            f"{body_text}\n\n"
            f"_Vui lòng bấm nút bên dưới để xác nhận thực thi hoặc bỏ qua nếu không đồng ý._"
        )
    else:
        # Thông báo cảnh báo thuần túy (không kèm action) giữ nguyên body từ client
        icon = "🔔" if severity == "INFO" else "⚠️" if severity == "WARNING" else "🚨"
        msg_text = f"{icon} *{title}*\n\n{body}"

    reply_markup = {"inline_keyboard": inline_keyboard} if inline_keyboard else None
    msg_id = await send_telegram_msg(ADMIN_USER_ID, msg_text, reply_markup=reply_markup)
    if not msg_id:
        append_audit_log("notify_event", title, {"severity": severity, "error": "telegram_send_failed"}, ADMIN_USER_ID, "FAILED", 0, 0)
        raise HTTPException(status_code=502, detail="Failed to dispatch message to Telegram")
    append_audit_log("notify_event", title, {"severity": severity, "actions": len(actions)}, ADMIN_USER_ID, "SENT", 0, 0)

    return {"status": "dispatched", "telegram_message_id": msg_id}


# --- 10. MAIN ENTRYPOINT WITH SINGLETON FLOCK ---
def main():
    # 1. Singleton Process Lock
    try:
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, BlockingIOError):
        print(f"[Error] Another instance of dgx-chatops is already running (locked by {LOCK_FILE}). Exiting.", file=sys.stderr)
        sys.exit(1)

    print("==================================================", flush=True)
    print("🚀 Khởi động DGX-ChatOps Universal Gateway Daemon", flush=True)
    print(f"   Listening on: 0.0.0.0:{CHATOPS_PORT}", flush=True)
    print(f"   Admin Telegram ID: {ADMIN_USER_ID}", flush=True)
    print("==================================================", flush=True)

    # 2. Run Uvicorn server (HTTP + Lifespan Telegram Poller)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=CHATOPS_PORT,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
