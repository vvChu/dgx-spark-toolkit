import os
import requests
import time

env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
proxy_url = ""
proxy_key = ""
with open(env_path, "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("GATEWAY_PROXY_URL="):
            proxy_url = line.split("=", 1)[1].strip()
        elif line.startswith("GATEWAY_PROXY_KEY="):
            proxy_key = line.split("=", 1)[1].strip()

models_to_test = [
    "gemini-3.1-flash-image",
    "gemini-3-pro-image"
]

endpoint = f"{proxy_url}/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {proxy_key}"
}

print("Testing exact model aliases directly on External Proxy...\n")

for model in models_to_test:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply 'OK'"}],
        "max_tokens": 10
    }
    start = time.time()
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        latency = time.time() - start
        if resp.status_code == 200:
            print(f"✅ {model}: Working (200) in {latency:.2f}s")
        else:
            print(f"❌ {model}: Failed ({resp.status_code}) in {latency:.2f}s - {resp.text[:100]}")
    except Exception as e:
        latency = time.time() - start
        print(f"⚠️ {model}: Timeout/Error in {latency:.2f}s - {e}")
