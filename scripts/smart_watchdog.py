import os
import time
import requests
import docker

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-spark-secure-key-2026")

# Giới hạn tần suất báo lỗi (Cooldown) để không bị spam (30 phút / 1 loại lỗi)
COOLDOWN_MINUTES = 30
last_alert_time = {}

def send_telegram_alert(message, alert_type):
    global last_alert_time
    now = time.time()
    if alert_type in last_alert_time:
        if now - last_alert_time[alert_type] < COOLDOWN_MINUTES * 60:
            return # Đang trong thời gian cooldown
            
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing Telegram Credentials!", flush=True)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🚨 **CẢNH BÁO TỪ SMART WATCHDOG** 🚨\n\n{message}",
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
        last_alert_time[alert_type] = now
        print(f"Sent alert for: {alert_type}", flush=True)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}", flush=True)

def check_docker_containers():
    try:
        client = docker.from_env()
        core_services = ['ai-gateway', 'qwen36b', 'milvus-standalone', 'rag-service']
        for service in core_services:
            try:
                container = client.containers.get(service)
                if container.status != "running":
                    send_telegram_alert(f"Container `{service}` hiện đang bị dừng (Status: {container.status}). Vui lòng kiểm tra ngay!", f"container_down_{service}")
            except docker.errors.NotFound:
                pass
    except Exception as e:
        print(f"Docker API Error: {e}", flush=True)

def check_vllm_deadlock():
    try:
        # Test 1: Khám Liveliness
        res = requests.get("http://qwen36b:8000/v1/models", timeout=5)
        if res.status_code != 200:
            send_telegram_alert("vLLM (qwen36b) không trả về kết nối ở port 8000! Có thể tiến trình đã sập.", "vllm_dead")
            return
            
        # Test 2: Khám Inference (Tránh Deadlock)
        payload = {
            "model": "qwen-local-primary",
            "messages": [{"role": "user", "content": "1"}],
            "max_tokens": 1
        }
        # Nếu quá 15s không ra được 1 token thì đích thị vLLM đang bị Deadlock/OOM
        res = requests.post("http://qwen36b:8000/v1/chat/completions", json=payload, timeout=15)
        if res.status_code != 200:
            send_telegram_alert(f"vLLM trả về lỗi HTTP {res.status_code} khi suy luận!", "vllm_error")
    except requests.exceptions.Timeout:
        send_telegram_alert("vLLM (Qwen 35B) bị kẹt (Timeout >15s) khi tính toán 1 token! Engine đang bị Deadlock hoặc OOM. Vui lòng chạy lệnh: `docker restart qwen36b`", "vllm_deadlock")
    except Exception as e:
        pass # Có thể container đang khởi động

def check_ai_gateway():
    try:
        payload = {
            "model": "rag-core",
            "messages": [{"role": "user", "content": "1"}],
            "max_tokens": 1
        }
        headers = {"Authorization": f"Bearer {LITELLM_MASTER_KEY}"}
        # Test gọi proxy (có timeout 45s để tính cả thời gian Fallback)
        res = requests.post("http://ai-gateway:4000/v1/chat/completions", json=payload, headers=headers, timeout=45)
        
        if res.status_code == 400:
            send_telegram_alert("AI Gateway trả về lỗi 400 Bad Request! Khả năng cấu hình Model ID hoặc Upstream Proxy đang bị sai lệch.", "gateway_400")
        elif res.status_code in [502, 503, 504]:
            send_telegram_alert(f"AI Gateway báo lỗi Server Error {res.status_code}. Luồng Fallback có thể đang gặp sự cố!", "gateway_50x")
    except requests.exceptions.Timeout:
        send_telegram_alert("AI Gateway bị treo hoàn toàn (Timeout >20s) và không thể chuyển hướng Fallback!", "gateway_timeout")
    except Exception as e:
        pass

def main():
    print("Smart Watchdog is starting...", flush=True)
    while True:
        check_docker_containers()
        check_vllm_deadlock()
        check_ai_gateway()
        # Chờ 60 phút (3600 giây) cho lần khám bệnh tiếp theo
        time.sleep(3600)

if __name__ == "__main__":
    main()
