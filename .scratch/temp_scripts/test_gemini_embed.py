import urllib.request
import urllib.error
import json
import socket
import sys

API_KEY = "sk-spark-secure-key-2026"
BASE_URL = "http://127.0.0.1:8090/v1"
MODEL = "gemini-embed"

print(f"Testing Gemini Embedding API via AI Gateway on 8090 for model '{MODEL}'...")

req_data = json.dumps({
    "model": MODEL,
    "input": ["Tôi là Antigravity, mô hình AI thông minh.", "Thử nghiệm Gemini Embedding API Free Tier."]
}).encode("utf-8")

req = urllib.request.Request(f"{BASE_URL}/embeddings", data=req_data)
req.add_header("Authorization", f"Bearer {API_KEY}")
req.add_header("Content-Type", "application/json")

try:
    with urllib.request.urlopen(req, timeout=15) as response:
        res_body = response.read().decode("utf-8")
        res_json = json.loads(res_body)
        
        # Verify the structure
        data = res_json.get("data", [])
        if data:
            print("✅ Success! Received embeddings successfully.")
            for idx, item in enumerate(data):
                embedding = item.get("embedding", [])
                print(f"  - Input {idx}: Embedding length = {len(embedding)}, Prefix = {embedding[:5]}...")
        else:
            print("❌ Failed: Response data is empty or invalid structure.")
            print(json.dumps(res_json, indent=2))
except urllib.error.HTTPError as e:
    print(f"❌ Failed (HTTP {e.code}: {e.reason})")
    try:
        err_body = e.read().decode("utf-8")
        print(f"Error Details: {err_body}")
    except Exception:
        pass
except urllib.error.URLError as e:
    if isinstance(e.reason, socket.timeout):
        print("❌ Failed (Timeout)")
    else:
        print(f"❌ Failed (Connection error: {e.reason})")
except Exception as e:
    print(f"❌ Failed ({e})")
