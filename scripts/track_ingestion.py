#!/usr/bin/env python3
import time
import os
import json
import requests
import subprocess
from datetime import timedelta
from pathlib import Path

# Load env vars manually to avoid python-dotenv dependency
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k] = v

# ================== CẤU HÌNH ==================
SOURCE_DIR = "/home/vvc/Documents/VB phap quy"
STATE_FILE = "/home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion_state.json"
UPDATE_INTERVAL = 10           # giây (10 giây)
TELEGRAM_ENABLED = True

# Màu sắc
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

def get_file_count():
    try:
        cmd = f'find "{SOURCE_DIR}" -type f -name "*.pdf" | wc -l'
        res = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
        return int(res.decode("utf-8").strip())
    except Exception:
        return 0

def get_processed_count():
    if not os.path.exists(STATE_FILE):
        return 0
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            return len(data.get("processed_files", {}))
    except Exception:
        return 0

def get_milvus_chunks():
    try:
        cmd = "docker exec rag-watcher python3 -c \"from pymilvus import connections, Collection; connections.connect(host='milvus-standalone', port='19530'); coll = Collection('legal_docs'); coll.flush(); print(coll.num_entities)\""
        res = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
        return int(res.decode('utf-8').strip())
    except:
        return 0

def get_gpu_memory_percent():
    try:
        output = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"]).decode()
        used, total = map(int, output.strip().split(','))
        return round((used / total) * 100, 1)
    except:
        return 0

def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": f"🚀 <b>RAG Ingestion</b>\n\n{message}",
        "parse_mode": "HTML"
    }, timeout=8)

# ================== MAIN ==================
def main():
    print(f"{GREEN}🚀 RAG Ingestion Live Tracking - Đang khởi động...{RESET}\n")

    total_files = get_file_count()
    start_time = time.time()
    start_files = get_processed_count()
    start_chunks = get_milvus_chunks()
    batch_count = start_files

    while True:
        current_files = get_processed_count()
        current_chunks = get_milvus_chunks()
        gpu_mem = get_gpu_memory_percent()
        elapsed = time.time() - start_time
        if elapsed < 1: elapsed = 1
        
        total_files_processed = current_files - start_files if current_files > start_files else 0
        total_chunks_processed = current_chunks - start_chunks if current_chunks > start_chunks else 0

        # Tính tốc độ trung bình từ lúc bật màn hình này
        speed_files = (total_files_processed / elapsed) * 60
        speed_chunks = (total_chunks_processed / elapsed) * 60
        eta = (total_files - current_files) / speed_files * 60 if speed_files > 0 else 0

        # Chọn màu
        if gpu_mem > 85:
            color = RED
            warning = " ⚠️ NGUY HIỂM - GẦN OOM!"
        elif gpu_mem > 75:
            color = YELLOW
            warning = " ⚠️ Memory cao"
        else:
            color = GREEN
            warning = ""

        # In bảng
        print(f"\033c", end="")  # clear màn hình
        print(f"{color}╔══════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{color}║                 RAG INGESTION LIVE TRACKING                 ║{RESET}")
        print(f"{color}╠══════════════════════════════════════════════════════════════╣{RESET}")
        print(f"  Tổng file PDF          : {total_files:,}")
        pct = (current_files/total_files*100) if total_files > 0 else 0
        print(f"  Đã xử lý               : {current_files:,} ({pct:6.2f}%)")
        print(f"  Chunks trong Milvus    : {current_chunks:,}")
        print(f"  Tốc độ                 : {speed_files:6.1f} file/phút | {speed_chunks:6.1f} chunks/phút")
        print(f"  Thời gian đã chạy      : {str(timedelta(seconds=int(elapsed)))}")
        print(f"  Ước tính còn lại       : {str(timedelta(seconds=int(eta)))}")
        print(f"  GPU Memory             : {gpu_mem:5.1f}%{warning}")
        print(f"{color}╚══════════════════════════════════════════════════════════════╝{RESET}")
        print("\n[ Nhấn Ctrl+C để thoát ]")

        if TELEGRAM_ENABLED:
            if current_files - batch_count >= 50:
                send_telegram(f"Batch hoàn thành!\nĐã xử lý: {current_files}/{total_files} file\nChunks: {current_chunks}\nThời gian: {str(timedelta(seconds=int(elapsed)))}")
                batch_count = current_files
            if current_files >= total_files and total_files > 0:
                send_telegram(f"🎉 <b>INGEST HOÀN TẤT TOÀN BỘ!</b>\nTổng file: {total_files}\nTổng chunks: {current_chunks}\nTổng thời gian: {str(timedelta(seconds=int(elapsed)))}")
                break

        # Không cần thay đổi last_files, nó sẽ dựa vào start_files để tính trung bình
        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    main()
