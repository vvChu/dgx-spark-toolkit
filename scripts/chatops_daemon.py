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
import shutil
import signal
import sys
import time
from typing import Any, Dict, List, Optional

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
CHATOPS_INTERNAL_SECRET = os.environ.get("CHATOPS_INTERNAL_SECRET", "dgx_spark_chatops_secret_2026").strip()
CHATOPS_EMERGENCY_PIN = os.environ.get("CHATOPS_EMERGENCY_PIN", "982631").strip()

LOG_DIR = PROJECT_ROOT / "logs" / "chatops"
LOG_DIR.mkdir(parents=True, exist_ok=True)

STATE_DIR = Path.home() / ".local" / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

LOCK_FILE = STATE_DIR / "dgx_chatops.lock"
LOCKOUT_FILE = STATE_DIR / "chatops_lockout.json"
AUDIT_FILE = LOG_DIR / "audit.jsonl"
COMMANDS_FILE = PROJECT_ROOT / "scripts" / "chatops_commands.yaml"

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Allowed internal networks for REST endpoint
ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
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

# --- 2. IN-MEMORY STATE & MUTEXES ---
action_cache: Dict[str, Dict[str, Any]] = {}
heavy_op_lock = asyncio.Lock()
service_locks: Dict[str, asyncio.Lock] = {}
last_audit_hash: str = "0" * 64


def get_service_lock(service_name: str) -> asyncio.Lock:
    """Returns or creates a per-service lock."""
    if service_name not in service_locks:
        service_locks[service_name] = asyncio.Lock()
    return service_locks[service_name]


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
    """Makes an async POST request to Telegram Bot API with timeout."""
    url = f"{TELEGRAM_API_BASE}/{method}"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
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
    """Sends a document file (.log) to Telegram."""
    url = f"{TELEGRAM_API_BASE}/sendDocument"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(file_path, "rb") as f:
                files = {"document": (file_path.name, f, "text/plain")}
                data = {"chat_id": str(chat_id), "caption": caption[:1000]}
                res = await client.post(url, data=data, files=files)
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
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=temperature.gpu,utilization.gpu",
            "--format=csv,noheader",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        if out:
            temp, util = out.decode().strip().split(",")
            lines.append(f"• *GPU Blackwell:* Nhiệt độ `{temp.strip()}°C` | Tải `{util.strip()}`")
    except Exception:
        pass

    lines.append("\n📦 *TRẠNG THÁI CONTAINERS:*")
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "-a",
            "--format",
            "{{.Names}}|{{.Status}}|{{.Image}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        if out:
            for c_line in out.decode().strip().split("\n"):
                if not c_line.strip():
                    continue
                parts = c_line.split("|")
                name = parts[0]
                status = parts[1]
                if any(core in name for core in ["open-webui", "ai-gateway", "qwen36b", "smart-watchdog", "cloudflared", "rag-service"]):
                    st_icon = "🟢" if "Up" in status else "🔴"
                    lines.append(f" {st_icon} `{name}`: {status}")
    except Exception as e:
        lines.append(f"• Lỗi kiểm tra Docker: {e}")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


async def probe_blackwell_gpu() -> str:
    """Deep probe for NVIDIA GB10 with compute processes memory summation."""
    lines = ["🎮 *THÔNG SỐ GPU NVIDIA BLACKWELL GB10* 🎮\n"]
    try:
        p1 = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=name,temperature.gpu,utilization.gpu,power.draw",
            "--format=csv,noheader",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out1, _ = await p1.communicate()
        if out1:
            name, temp, util, power = [x.strip() for x in out1.decode().strip().split(",")]
            lines.append(f"• Thiết bị: `{name}`")
            lines.append(f"• Nhiệt độ: `{temp}°C` | Tải: `{util}` | Công suất: `{power}`")

        # Query compute processes
        p2 = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-compute-apps=process_name,used_memory",
            "--format=csv,noheader",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out2, _ = await p2.communicate()
        apps = []
        total_used_mib = 0.0
        if out2:
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
        lines.append(f"• Lỗi truy vấn GPU: {e}")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


async def execute_shell_job(
    cmd: str,
    job_id: str,
    chat_id: int,
    status_msg_id: int,
    title: str,
    timeout: int = 120,
) -> None:
    """Executes a subprocess with real-time feedback and Two-Tier Delivery."""
    start_time = time.time()
    await edit_telegram_msg(chat_id, status_msg_id, f"⏳ *[ĐANG CHẠY]* `{title}`\nJob ID: `{job_id}`\nVui lòng đợi...")

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
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
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
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

        duration_ms = int((time.time() - start_time) * 1000)
        exit_code = proc.returncode or 0
        out_text = (stdout_bytes or b"").decode("utf-8", errors="replace")
        err_text = (stderr_bytes or b"").decode("utf-8", errors="replace")
        full_output = (out_text + "\n" + err_text).strip()

        log_file = LOG_DIR / f"job_{job_id}_{int(time.time())}.log"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"Command: {cmd}\nExit Code: {exit_code}\nDuration: {duration_ms}ms\n\n{full_output}")

        status_icon = "✅" if exit_code == 0 else "❌"
        status_text = "THÀNH CÔNG" if exit_code == 0 else f"THẤT BẠI (Exit {exit_code})"

        # Two-Tier Output Logic
        if len(full_output) <= 2000 and exit_code == 0:
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

        append_audit_log("exec", cmd, {"job_id": job_id}, ADMIN_USER_ID, "SUCCESS" if exit_code == 0 else "FAILED", duration_ms, exit_code, full_output[:200])

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
    """Builds the main interactive dashboard keyboard."""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Xem Toàn Bộ Status", "callback_data": "menu:status"},
                {"text": "🎮 GPU Blackwell", "callback_data": "menu:gpu"},
            ],
            [
                {"text": "🔄 Khởi Động Lại Service", "callback_data": "menu:restart_list"},
                {"text": "📦 Nâng Cấp Open WebUI", "callback_data": "menu:upgrade_owu"},
            ],
            [
                {"text": "📄 Hàng Đợi RAG Ingestion", "callback_data": "menu:rag_state"},
                {"text": "❓ Hướng Dẫn ChatOps", "callback_data": "menu:help"},
            ],
        ]
    }


def get_restart_service_markup() -> Dict[str, Any]:
    """Builds sub-menu for restarting services."""
    services = ["open-webui", "qwen36b", "ai-gateway", "smart-watchdog", "cloudflared-tunnel", "rag-service"]
    keyboard = []
    for i in range(0, len(services), 2):
        row = [{"text": f"🔄 {services[i]}", "callback_data": f"rst:{services[i]}"}]
        if i + 1 < len(services):
            row.append({"text": f"🔄 {services[i+1]}", "callback_data": f"rst:{services[i+1]}"})
        keyboard.append(row)
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
    """Probes RAG pipeline service health and vector store connections."""
    lines = ["📄 *TIẾN ĐỘ & TRẠNG THÁI RAG INGESTION PIPELINE* 📄\n"]
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.get("http://127.0.0.1:8005/health")
            if res.status_code == 200:
                data = res.json()
                lines.append("• Dịch vụ `rag-service`: 🟢 Khả dụng (Port 8005)")
                lines.append(f"• Phiên bản: `{data.get('version', '2.0.0')}`")
                checks = data.get("checks", {})
                for db_name, db_st in checks.items():
                    st_icon = "🟢" if db_st == "ok" else "🔴"
                    lines.append(f"  └─ `{db_name}`: {st_icon} {db_st}")
            else:
                lines.append(f"• Dịch vụ `rag-service`: ⚠️ Phản hồi HTTP {res.status_code}")
    except Exception as e:
        lines.append(f"• Dịch vụ `rag-service`: 🔴 Không thể kết nối ({e})")

    # Ingestion queue or status files
    ingest_dir = PROJECT_ROOT / "data" / "raw"
    processed_dir = PROJECT_ROOT / "data" / "processed"
    if ingest_dir.exists():
        raw_count = len(list(ingest_dir.glob("*.*")))
        lines.append(f"• Tệp chờ xử lý (`data/raw`): `{raw_count}` tệp")
    if processed_dir.exists():
        proc_count = len(list(processed_dir.glob("*.*")))
        lines.append(f"• Tệp đã lập chỉ mục (`data/processed`): `{proc_count}` tệp")

    lines.append(f"\n_Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}_")
    return "\n".join(lines)


async def dispatch_command(
    command_id: str,
    params: Dict[str, Any],
    chat_id: int,
    message_id: int,
    title: str = "",
    cq_id: Optional[str] = None,
    timeout: Optional[int] = None,
) -> None:
    """Universal dispatcher for commands defined in chatops_commands.yaml or emergency shell."""
    # Special handling for emergency shell execution
    if command_id == "system.emergency.exec":
        shell_cmd = params.get("cmd", "")
        job_id = hashlib.md5(f"exec_{time.time()}".encode()).hexdigest()[:6]
        await execute_shell_job(shell_cmd, job_id, chat_id, message_id, title or f"Khẩn cấp: {shell_cmd[:30]}", timeout=timeout or 60)
        return

    registry = load_command_registry()
    cmd_def = registry.get(command_id)

    if not cmd_def:
        err_text = f"❌ *[LỖI]* Lệnh `{command_id}` chưa được định nghĩa trong `chatops_commands.yaml`!"
        if not await edit_telegram_msg(chat_id, message_id, err_text, reply_markup=get_main_dashboard_markup()):
            await send_telegram_msg(chat_id, err_text, reply_markup=get_main_dashboard_markup())
        return

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
            err_msg = f"❌ *[LỖI THAM SỐ]* Giá trị `{p_val}` của tham số `{p_name}` không thỏa mãn mẫu an toàn `{p_pattern}`!"
            if not await edit_telegram_msg(chat_id, message_id, err_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, err_msg, reply_markup=get_main_dashboard_markup())
            return

    # 2. Resolve Service Lock Name
    svc_lock_name = None
    if service_lock_tmpl:
        try:
            svc_lock_name = service_lock_tmpl.format(**params)
        except KeyError:
            svc_lock_name = service_lock_tmpl

    # 3. Check Mutex Locks
    if is_heavy and heavy_op_lock.locked():
        if cq_id:
            await answer_callback(cq_id, "⚠️ Đang có một tác vụ nặng khác đang chạy!", show_alert=True)
        warn_msg = "⚠️ *Đang có một tác vụ nặng khác đang chạy trên server. Vui lòng thử lại sau!*"
        if not await edit_telegram_msg(chat_id, message_id, warn_msg, reply_markup=get_main_dashboard_markup()):
            await send_telegram_msg(chat_id, warn_msg, reply_markup=get_main_dashboard_markup())
        return

    if svc_lock_name:
        s_lock = get_service_lock(svc_lock_name)
        if s_lock.locked():
            if cq_id:
                await answer_callback(cq_id, f"⚠️ Dịch vụ {svc_lock_name} đang bận!", show_alert=True)
            busy_msg = f"⚠️ *Dịch vụ `{svc_lock_name}` đang có tác vụ khác thực thi. Vui lòng thử lại sau!*"
            if not await edit_telegram_msg(chat_id, message_id, busy_msg, reply_markup=get_main_dashboard_markup()):
                await send_telegram_msg(chat_id, busy_msg, reply_markup=get_main_dashboard_markup())
            return

    # 4. Executor implementation
    async def _execute_action():
        if runner == "internal":
            if cq_id:
                await answer_callback(cq_id)
            if command_id == "system.status":
                text = await probe_hardware_and_containers()
                if not await edit_telegram_msg(chat_id, message_id, text, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, text, reply_markup=get_main_dashboard_markup())
                append_audit_log("internal_cmd", command_id, params, ADMIN_USER_ID, "SUCCESS", 0, 0, "Probed system status")
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
            else:
                unhandled = f"⚠️ Chưa xử lý runner internal cho lệnh `{command_id}`"
                if not await edit_telegram_msg(chat_id, message_id, unhandled, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, unhandled, reply_markup=get_main_dashboard_markup())
        elif runner in ["docker_cli", "host_script"]:
            target_tmpl = cmd_def.get("target", "")
            try:
                rendered_cmd = target_tmpl.format(**params)
            except KeyError as ke:
                err_text = f"❌ *[LỖI CẤU HÌNH]* Thiếu tham số `{ke}` cho lệnh `{command_id}`!"
                if not await edit_telegram_msg(chat_id, message_id, err_text):
                    await send_telegram_msg(chat_id, err_text)
                return

            job_id = hashlib.md5(f"{command_id}_{time.time()}".encode()).hexdigest()[:6]
            await execute_shell_job(rendered_cmd, job_id, chat_id, message_id, title, timeout=cmd_timeout)
        else:
            invalid_runner = f"❌ *[LỖI]* Runner `{runner}` không hợp lệ!"
            if not await edit_telegram_msg(chat_id, message_id, invalid_runner):
                await send_telegram_msg(chat_id, invalid_runner)

    # 5. Run with proper locks
    if is_heavy and svc_lock_name:
        async with heavy_op_lock:
            async with get_service_lock(svc_lock_name):
                await _execute_action()
    elif is_heavy:
        async with heavy_op_lock:
            await _execute_action()
    elif svc_lock_name:
        async with get_service_lock(svc_lock_name):
            await _execute_action()
    else:
        await _execute_action()


# --- 8. TELEGRAM LONG POLLER ENGINE ---
async def process_telegram_update(update: Dict[str, Any]) -> None:
    """Processes an incoming Telegram update with strict ACL and atomic actions."""
    # Handle callback queries (Button clicks)
    if "callback_query" in update:
        cq = update["callback_query"]
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
        if data == "menu:main":
            await answer_callback(cq_id)
            await edit_telegram_msg(chat_id, message_id, "🖥️ *BẢNG ĐIỀU KHIỂN DGX SPARK CHATOPS*\nVui lòng chọn tác vụ bên dưới:", reply_markup=get_main_dashboard_markup())
            return
        elif data == "menu:status":
            await dispatch_command("system.status", {}, chat_id, message_id, cq_id=cq_id)
            return
        elif data == "menu:gpu":
            await dispatch_command("host.gpu", {}, chat_id, message_id, cq_id=cq_id)
            return
        elif data == "menu:rag_state":
            await dispatch_command("rag.ingestion.state", {}, chat_id, message_id, cq_id=cq_id)
            return
        elif data == "menu:restart_list":
            await answer_callback(cq_id)
            await edit_telegram_msg(chat_id, message_id, "🔄 *CHỌN SERVICE CẦN KHỞI ĐỘNG LẠI:*", reply_markup=get_restart_service_markup())
            return
        elif data.startswith("rst:"):
            svc = data.split(":", 1)[1]
            await dispatch_command("system.container.restart", {"service": svc}, chat_id, message_id, title=f"Khởi động lại {svc}", cq_id=cq_id)
            return
        elif data == "menu:upgrade_owu":
            await answer_callback(cq_id)
            prompt = (
                "⚠️ *XÁC NHẬN NÂNG CẤP OPEN WEBUI*\n"
                "• Lệnh sẽ chạy: `bash scripts/update-openwebui.sh v0.11.4`\n"
                "• Snapshot database tự động, an toàn 100% (Zero Data Loss).\n"
                "• Thời gian gián đoạn dự kiến: ~30s.\n\n"
                "Bạn có chắc chắn muốn thực thi ngay bây giờ?"
            )
            nonce = hashlib.sha256(f"upg_owu_{time.time()}".encode()).hexdigest()[:8]
            action_cache[nonce] = {
                "command": "system.openwebui.upgrade",
                "params": {"target_version": "v0.11.4"},
                "title": "Nâng cấp Open WebUI lên v0.11.4",
                "timeout": 300,
                "expires": time.time() + 60,
            }
            markup = {
                "inline_keyboard": [
                    [{"text": "✅ XÁC NHẬN NÂNG CẤP", "callback_data": f"act:{nonce}"}],
                    [{"text": "❌ HỦY BỎ", "callback_data": "menu:main"}],
                ]
            }
            await edit_telegram_msg(chat_id, message_id, prompt, reply_markup=markup)
            return
        elif data == "menu:help":
            await answer_callback(cq_id)
            help_text = (
                "❓ *HƯỚNG DẪN SỬ DỤNG DGX-CHATOPS*\n\n"
                "• `/menu` hoặc `/start`: Bật bảng điều khiển cảm ứng.\n"
                "• `/status`: Kiểm tra nhanh phần cứng & containers.\n"
                "• `/gpu`: Xem nhiệt độ, VRAM GPU Blackwell GB10.\n"
                "• `/rag_state`: Xem tiến độ hàng đợi RAG Ingestion.\n"
                "• `/restart <service>`: Khởi động lại container.\n"
                "• `/upgrade_owu`: Nâng cấp Open WebUI.\n"
                "• `/exec <PIN> <command>`: Thực thi lệnh khẩn cấp (có 2-step confirmation).\n"
            )
            await edit_telegram_msg(chat_id, message_id, help_text, reply_markup=get_main_dashboard_markup())
            return

        # 2. Dynamic Action Buttons (act:<nonce>)
        if data.startswith("act:"):
            nonce = data.split(":", 1)[1]
            entry = action_cache.pop(nonce, None)
            if not entry or time.time() > entry.get("expires", 0):
                await answer_callback(cq_id, "⚠️ Nút bấm đã hết hạn hoặc đã được thực thi!", show_alert=True)
                expired_msg = "⚠️ *Thao tác đã hết hạn hoặc đã được thực thi trước đó.*"
                if not await edit_telegram_msg(chat_id, message_id, expired_msg, reply_markup=get_main_dashboard_markup()):
                    await send_telegram_msg(chat_id, expired_msg, reply_markup=get_main_dashboard_markup())
                return

            await answer_callback(cq_id, "Đang xử lý tác vụ...")
            cmd = entry["command"]
            params = entry.get("params", {})
            title = entry.get("title", "")
            timeout = entry.get("timeout")
            await dispatch_command(cmd, params, chat_id, message_id, title=title, cq_id=cq_id, timeout=timeout)
            return

        return

    # Handle incoming text messages
    if "message" in update:
        msg = update["message"]
        chat_id = msg.get("chat", {}).get("id")
        user_id = msg.get("from", {}).get("id")
        message_id = msg.get("message_id")
        text = msg.get("text", "").strip()

        # Strict ACL
        if user_id != ADMIN_USER_ID:
            append_audit_log("message", text, {"user_id": user_id}, user_id, "FORBIDDEN", 0, -1, "Unknown user message dropped")
            return

        # 1. /start or /menu
        if text in ["/start", "/menu"]:
            await send_telegram_msg(chat_id, "🖥️ *BẢNG ĐIỀU KHIỂN DGX SPARK CHATOPS*\nVui lòng chọn tác vụ bên dưới:", reply_markup=get_main_dashboard_markup())
            return

        # 2. /status
        if text == "/status":
            sent_id = await send_telegram_msg(chat_id, "⏳ Đang kiểm tra trạng thái...")
            if sent_id:
                await dispatch_command("system.status", {}, chat_id, sent_id)
            return

        # 3. /gpu
        if text == "/gpu":
            sent_id = await send_telegram_msg(chat_id, "⏳ Đang truy vấn GPU Blackwell...")
            if sent_id:
                await dispatch_command("host.gpu", {}, chat_id, sent_id)
            return

        # 4. /rag_state
        if text == "/rag_state":
            sent_id = await send_telegram_msg(chat_id, "⏳ Đang kiểm tra hàng đợi RAG...")
            if sent_id:
                await dispatch_command("rag.ingestion.state", {}, chat_id, sent_id)
            return

        # 5. /restart <service>
        if text.startswith("/restart"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await send_telegram_msg(chat_id, "Cú pháp: `/restart <service_name>` (Ví dụ: `/restart open-webui`)")
                return
            svc = parts[1].strip()
            sent_id = await send_telegram_msg(chat_id, f"⏳ Đang chuẩn bị khởi động lại {svc}...")
            if sent_id:
                await dispatch_command("system.container.restart", {"service": svc}, chat_id, sent_id, title=f"Khởi động lại {svc}")
            return

        # 6. /upgrade_owu [version]
        if text.startswith("/upgrade_owu"):
            parts = text.split(maxsplit=1)
            ver = parts[1].strip() if len(parts) > 1 else "v0.11.4"
            sent_id = await send_telegram_msg(chat_id, f"⏳ Đang chuẩn bị nâng cấp Open WebUI lên {ver}...")
            if sent_id:
                await dispatch_command("system.openwebui.upgrade", {"target_version": ver}, chat_id, sent_id, title=f"Nâng cấp Open WebUI lên {ver}")
            return

        # 7. /exec <PIN> <command>
        if text.startswith("/exec"):
            # Immediately delete message to purge PIN from history
            await delete_telegram_msg(chat_id, message_id)

            remaining_lock = check_brute_force_lockout()
            if remaining_lock:
                await send_telegram_msg(chat_id, f"🚨 *LỆNH /EXEC ĐANG BỊ KHÓA!* Vui lòng thử lại sau `{remaining_lock//60} phút {remaining_lock%60} giây`.")
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


# --- 9. FASTAPI INTERNAL REST SERVER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Wait for network
    print("[ChatOps] Checking network connectivity...", flush=True)
    for _ in range(12):
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get("https://api.telegram.org", timeout=4.0)
                if res.status_code in [200, 302, 404]:
                    print("[ChatOps] Network and Telegram API reachable.", flush=True)
                    break
        except Exception:
            await asyncio.sleep(3)

    # 2. Reset Webhook
    await telegram_request("deleteWebhook", {"drop_pending_updates": False})

    # 3. Start Telegram Polling Task
    poller_task = asyncio.create_task(telegram_polling_loop())

    yield

    # 4. Graceful Shutdown
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass
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


@app.post("/api/v1/notify")
async def handle_internal_notify(payload: Dict[str, Any], x_chatops_secret: Optional[str] = Header(None)):
    """Receives alerts from Docker containers and sends Telegram messages with interactive buttons."""
    if not x_chatops_secret or not hmac.compare_digest(x_chatops_secret, CHATOPS_INTERNAL_SECRET):
        raise HTTPException(status_code=401, detail="Invalid ChatOps Secret Header")

    title = payload.get("title", "Thông báo từ máy chủ DGX Spark")
    body = payload.get("body", "")
    severity = payload.get("severity", "INFO")
    actions = payload.get("actions", [])

    icon = "🔔" if severity == "INFO" else "⚠️" if severity == "WARNING" else "🚨"
    msg_text = f"{icon} *{title}*\n\n{body}"

    inline_keyboard = []
    for act in actions:
        action_id = act.get("action_id", "act")
        label = act.get("label", "Thực thi")
        cmd = act.get("command", "")
        params = act.get("params", {})
        timeout = act.get("timeout", 120)

        nonce = hashlib.sha256(f"{action_id}_{time.time()}_{label}".encode()).hexdigest()[:8]
        action_cache[nonce] = {
            "command": cmd,
            "params": params,
            "title": label,
            "timeout": timeout,
            "expires": time.time() + act.get("ttl_seconds", 3600),
        }
        inline_keyboard.append([{"text": label, "callback_data": f"act:{nonce}"}])

    reply_markup = {"inline_keyboard": inline_keyboard} if inline_keyboard else None
    msg_id = await send_telegram_msg(ADMIN_USER_ID, msg_text, reply_markup=reply_markup)
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
