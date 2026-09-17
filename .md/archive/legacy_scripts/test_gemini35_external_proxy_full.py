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

headers = {
    "Authorization": f"Bearer {proxy_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": "gemini-3.5-flash-low",
    "messages": [{"role": "user", "content": "Explain why gravity holds things in 2 sentences."}],
    "thinking_level": "low",
    "max_tokens": 100
}

try:
    print(f"Sending request to {proxy_url}/chat/completions ...")
    resp = requests.post(f"{proxy_url}/chat/completions", headers=headers, json=payload, timeout=15)
    print(f"Status Code: {resp.status_code}")
    print("Response JSON:")
    print(json.dumps(resp.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
