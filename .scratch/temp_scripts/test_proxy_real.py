import urllib.request
import urllib.error
import json
import socket
import sys

API_KEY = "sk-spark-secure-key-2026"
BASE_URL = "http://127.0.0.1:8090/v1"

models_to_test = [
    "gpt-oss-120b-medium",
    "gemini-3.1-pro-low",
    "gemini-3.1-flash-lite",
    "claude-sonnet-4-6",
    "rag-core"
]

print("Starting connectivity test using API Proxy on 8090 with master key...")

for model in models_to_test:
    print(f"- Testing {model}... ", end="", flush=True)
    req_data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply with 'OK'."}],
        "max_tokens": 10
    }).encode("utf-8")
    
    req = urllib.request.Request(f"{BASE_URL}/chat/completions", data=req_data)
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            print(f"✅ Success (Reply: {reply})")
    except urllib.error.HTTPError as e:
        print(f"❌ Failed (HTTP {e.code}: {e.reason})")
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout):
            print("❌ Failed (Timeout)")
        else:
            print(f"❌ Failed (Connection error: {e.reason})")
    except Exception as e:
        print(f"❌ Failed ({e})")
