import os
import urllib.request
import urllib.error
import json
import socket
import sys

API_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-spark-secure-key-2026")
BASE_URL = "http://127.0.0.1:8090/v1"
MODEL = "gemini-3.5-flash-medium"

print(f"Testing local AI Gateway connection for model '{MODEL}' with thinking_budget parameters...")

# We pass 'thinking_budget' in the payload. The custom callback on the local gateway 
# will intercept it, convert it to 'thinking_level = medium', strip thinking_budget to avoid 400,
# and route it to direct Google API.
payload = {
    "model": MODEL,
    "messages": [
        {"role": "user", "content": "Hãy viết một câu danh ngôn ngắn gọn truyền cảm hứng về học tập."}
    ],
    "max_tokens": 150,
    "thinking_budget": 1024
}

print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
req_data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(f"{BASE_URL}/chat/completions", data=req_data)
req.add_header("Authorization", f"Bearer {API_KEY}")
req.add_header("Content-Type", "application/json")

try:
    with urllib.request.urlopen(req, timeout=30) as response:
        res_body = response.read().decode("utf-8")
        res_json = json.loads(res_body)
        
        print("✅ SUCCESS!")
        reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"Reply:\n{reply}")
        
        # Check usage
        usage = res_json.get("usage", {})
        print(f"Usage Info: {json.dumps(usage)}")
        
except urllib.error.HTTPError as e:
    print(f"❌ FAILED (HTTP {e.code}: {e.reason})")
    try:
        err_body = e.read().decode("utf-8")
        print(f"Error Details: {err_body}")
    except Exception:
        pass
except urllib.error.URLError as e:
    print(f"❌ FAILED (Connection error: {e.reason})")
except Exception as e:
    print(f"❌ FAILED ({e})")
