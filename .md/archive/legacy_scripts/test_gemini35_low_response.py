import os
import requests
import json

env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
proxy_url = "http://100.79.241.120:8045/v1"
proxy_key = "sk-9a13a60d641a42f9a74b18d58d44a358"

if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GATEWAY_PROXY_URL="):
                proxy_url = line.split("=", 1)[1].strip()
            elif line.startswith("GATEWAY_PROXY_KEY="):
                proxy_key = line.split("=", 1)[1].strip()

payload = {
    "model": "gemini-3.5-flash-low",
    "messages": [{"role": "user", "content": "Hello! Say test."}],
    "max_tokens": 20
}
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {proxy_key}"
}

try:
    print(f"Querying gemini-3.5-flash-low on {proxy_url}...")
    resp = requests.post(f"{proxy_url}/chat/completions", headers=headers, json=payload, timeout=10)
    print(f"Status Code: {resp.status_code}")
    print("Response JSON:")
    print(json.dumps(resp.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
