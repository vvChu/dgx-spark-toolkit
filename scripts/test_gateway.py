import requests
import time
import urllib3
urllib3.disable_warnings()

GATEWAY_URL = "http://127.0.0.1:8090/v1/chat/completions"
HEADERS = {
    "Authorization": "Bearer sk-spark-secure-key-2026",
    "Content-Type": "application/json"
}

MODELS_TO_TEST = [
    "rag-core",                 # Base local model
    "ocr-tier4",                # Direct Google API (gemini-2.5-flash)
    "reasoning-fallback",       # Direct Google API (gemma-4-26b-a4b-it)
    "gemini-2.5-flash-lite",    # Proxy mapped model (with fallback)
    "gemini-3.1-flash-lite"     # Another Proxy model
]

print("=== BẮT ĐẦU TEST KẾT NỐI TOÀN DIỆN LITELLM GATEWAY ===\n")

for model in MODELS_TO_TEST:
    print(f"[*] Đang test model: {model} ...", end="", flush=True)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hãy phản hồi ngắn gọn bằng 1 câu: Xin chào!"}],
        "max_tokens": 50,
        "temperature": 0.7
    }
    
    start_time = time.time()
    try:
        response = requests.post(GATEWAY_URL, headers=HEADERS, json=payload, timeout=45)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            actual_model = result.get("model", "unknown")
            print(f" ✅ THÀNH CÔNG ({duration:.2f}s)")
            print(f"    - Model thực thi: {actual_model}")
            print(f"    - Phản hồi: {content}\n")
        else:
            print(f" ❌ THẤT BẠI ({duration:.2f}s)")
            print(f"    - Lỗi HTTP {response.status_code}: {response.text}\n")
    except requests.exceptions.Timeout:
        print(f" ⏳ TIMEOUT sau 45s\n")
    except Exception as e:
        print(f" 💥 LỖI KẾT NỐI: {e}\n")

print("=== HOÀN TẤT TEST ===")
