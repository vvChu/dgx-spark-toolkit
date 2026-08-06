import os
import requests
from requests.exceptions import Timeout

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

# List of models from the screenshot
models_to_test = [
    "gemini-3.1-pro-low",
    "gemini-2.5-pro",
    "gemini-3-flash-agent",
    "gemini-3-flash",
    "gemini-2.5-flash-thinking",
    "gemini-3.1-flash-image",
    "gpt-oss-120b-medium",
    "gemini-pro-agent",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.1-pro-high",
    "gemini-2.5-flash",
    "claude-opus-4-6-thinking",
    "claude-sonnet-4-6",
    "gemini-3-pro-image"
]

print(f"Proxy URL: {proxy_url}")
print(f"Testing {len(models_to_test)} models...\n")

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {proxy_key}"
}

endpoint = f"{proxy_url}/chat/completions"

for model in models_to_test:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 10
    }
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"✅ {model}: OK (200)")
        elif resp.status_code == 429:
            print(f"⚠️ {model}: Rate Limited (429)")
        elif resp.status_code == 400:
            print(f"❌ {model}: Bad Request (400) - {resp.text[:50]}")
        else:
            print(f"❌ {model}: Error ({resp.status_code}) - {resp.text[:50]}")
    except Timeout:
        print(f"❌ {model}: Timeout")
    except Exception as e:
        print(f"❌ {model}: Failed - {e}")
