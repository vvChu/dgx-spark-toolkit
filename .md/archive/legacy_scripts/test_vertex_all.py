import os, requests

env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
proxy_url, proxy_key = "", ""
with open(env_path, "r") as f:
    for line in f:
        if line.startswith("GATEWAY_PROXY_URL="): proxy_url = line.split("=", 1)[1].strip()
        elif line.startswith("GATEWAY_PROXY_KEY="): proxy_key = line.split("=", 1)[1].strip()

endpoint = f"{proxy_url}/chat/completions"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {proxy_key}"}

models_to_test = [
    "vertex_ai/gemini-2.5-flash",
    "vertex_ai/gemini-3.1-flash-image-preview",
    "vertex_ai/gemini-3.1-pro-preview"
]

for model in models_to_test:
    print(f"Testing model: {model}...")
    payload = {"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 10}
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")
