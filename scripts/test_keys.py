import os
import requests

env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
keys = {}
with open(env_path, "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("GEMINI_API_KEY_") and "=" in line:
            k, v = line.split("=", 1)
            v = v.split("#")[0].strip()
            if v and v != "placeholder_key" and "AIzaSy" in v:
                keys[k] = v

print(f"Found {len(keys)} active-looking keys. Testing them...")

for k, v in keys.items():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={v}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            print(f"✅ {k}: OK (200)")
        elif resp.status_code == 429:
            print(f"⚠️ {k}: Rate Limited (429)")
        else:
            print(f"❌ {k}: Error ({resp.status_code}) - {resp.text[:50]}")
    except Exception as e:
        print(f"❌ {k}: Connection Failed - {e}")
