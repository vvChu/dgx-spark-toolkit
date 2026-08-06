import urllib.request
import urllib.error
import json
import socket
import sys

API_KEY = "sk-9a13a60d641a42f9a74b18d58d44a358"
BASE_URL = "http://127.0.0.1:8045/v1"

models_to_test = [
    "gpt-oss-120b-medium",
    "gemini-3.1-pro-low",
    "claude-sonnet-4-6",
    "rag-core",
    "ocr-primary"
]

print("Starting connectivity test...")

for model in models_to_test:
    print(f"Testing model: {model} ...", end=" ", flush=True)
    req_data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply OK"}],
        "max_tokens": 5
    }).encode("utf-8")
    
    req = urllib.request.Request(f"{BASE_URL}/chat/completions", data=req_data)
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            print(f"SUCCESS (Reply: {reply})")
    except urllib.error.HTTPError as e:
        print(f"FAILED (HTTP {e.code})")
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout):
            print("FAILED (Timeout)")
        else:
            print(f"FAILED (Connection error: {e.reason})")
    except Exception as e:
        print(f"FAILED ({e})")
