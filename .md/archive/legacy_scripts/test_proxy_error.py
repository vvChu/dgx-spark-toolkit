import os, requests

env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
proxy_url, proxy_key = "", ""
with open(env_path, "r") as f:
    for line in f:
        if line.startswith("GATEWAY_PROXY_URL="): proxy_url = line.split("=", 1)[1].strip()
        elif line.startswith("GATEWAY_PROXY_KEY="): proxy_key = line.split("=", 1)[1].strip()

endpoint = f"{proxy_url}/chat/completions"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {proxy_key}"}

payload = {"model": "gemini-2.5-flash-thinking", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 10}
resp = requests.post(endpoint, headers=headers, json=payload, timeout=10)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")
