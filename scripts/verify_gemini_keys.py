import os
import urllib.request
import urllib.error
import json

env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
keys_to_test = {}

# 1. Parse keys from .env
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GEMINI_API_KEY"):
                # Handle commented out ones
                if line.startswith("#"):
                    continue
                parts = line.split("=", 1)
                if len(parts) == 2:
                    name = parts[0].strip()
                    val = parts[1].strip()
                    keys_to_test[name] = val

print(f"Loaded {len(keys_to_test)} Gemini API keys from `.env` to verify.\n")

# 2. Test each key against the new gemini-embedding-2 API directly
for name, key in sorted(keys_to_test.items()):
    if not key or "placeholder" in key.lower():
        print(f"⚠️ {name}: Skipped (Placeholder/Empty value: '{key}')")
        continue
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={key}"
    payload = json.dumps({
        "content": {
            "parts": [{"text": "Kiểm tra kết nối Gemini Embedding."}]
        }
    }).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"[*] Testing {name} ({key[:10]}...{key[-5:] if len(key) > 10 else ''}) ... ", end="", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            embedding = res_json.get("embedding", {}).get("values", [])
            if embedding:
                print(f"✅ VALID! (Embedding dim: {len(embedding)})")
            else:
                print("❌ INVALID (Empty response)")
    except urllib.error.HTTPError as e:
        err_msg = ""
        try:
            err_msg = e.read().decode("utf-8")
            err_json = json.loads(err_msg)
            err_msg = err_json.get("error", {}).get("message", err_msg)
        except Exception:
            pass
        print(f"❌ INVALID (HTTP {e.code}: {e.reason}) -> {err_msg[:120]}")
    except Exception as e:
        print(f"❌ ERROR ({e})")

print("\nVerification complete.")
