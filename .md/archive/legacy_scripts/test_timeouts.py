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

models_to_test = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-thinking",
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "gemini-3.1-flash-lite"
]

print(f"Proxy URL: {proxy_url}")
print("Testing with 60s timeout...\n")

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
    # For the one that gave 400 Bad request, we can't easily pass drop_params in standard OpenAI API call directly without LiteLLM proxy, wait, we are calling a proxy. If the proxy fails, it's on the proxy side.
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            print(f"✅ {model}: OK (200)")
        elif resp.status_code == 400:
            print(f"❌ {model}: Bad Request (400) - {resp.text[:50]}")
        else:
            print(f"❌ {model}: Error ({resp.status_code}) - {resp.text[:50]}")
    except Timeout:
        print(f"❌ {model}: Timeout (>60s)")
    except Exception as e:
        print(f"❌ {model}: Failed - {e}")
