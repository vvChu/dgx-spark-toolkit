import time
import requests
import json

url = "http://127.0.0.1:8004/v1/chat/completions"
headers = {"Content-Type": "application/json"}
data = {
    "model": "qwen-local-primary",
    "messages": [{"role": "user", "content": "Viết một bài luận ngắn khoảng 300 chữ phân tích về tiềm năng của AI trong tương lai."}],
    "max_tokens": 500,
    "temperature": 0.7
}

print("Đang gửi yêu cầu benchmark đến Qwen 35B (Port 8004)...")
try:
    start_time = time.time()
    response = requests.post(url, headers=headers, json=data, timeout=120)
    end_time = time.time()
    
    if response.status_code == 200:
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        tokens = result["usage"]["completion_tokens"]
        duration = end_time - start_time
        speed = tokens / duration
        print("\n=== KẾT QUẢ BENCHMARK QWEN 35B ===")
        print(f"⏳ Thời gian tổng cộng: {duration:.2f} giây")
        print(f"📝 Số token sinh ra: {tokens} tokens")
        print(f"🚀 Tốc độ (Throughput): {speed:.2f} tokens/giây")
        print("-" * 40)
        print("Trích dẫn phản hồi:")
        print(f"{content[:200]}...")
    else:
        print(f"Lỗi từ vLLM: HTTP {response.status_code} - {response.text}")
except requests.exceptions.ConnectionError:
    print("Lỗi: Không thể kết nối. vLLM vẫn đang nạp weights vào VRAM, chưa mở cổng 8004.")
except Exception as e:
    print(f"Lỗi: {e}")
