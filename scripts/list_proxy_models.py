import os
import requests
import json

project_root = os.environ.get("WORKSPACE_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.environ.get("ENV_FILE") or os.path.join(project_root, ".env")
proxy_url = os.environ.get("GATEWAY_PROXY_URL", "http://127.0.0.1:8045/v1")
proxy_key = os.environ.get("GATEWAY_PROXY_KEY", "")

if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GATEWAY_PROXY_URL="):
                proxy_url = line.split("=", 1)[1].strip()
            elif line.startswith("GATEWAY_PROXY_KEY="):
                proxy_key = line.split("=", 1)[1].strip()

try:
    resp = requests.get(f"{proxy_url}/models", headers={"Authorization": f"Bearer {proxy_key}"}, timeout=8)
    if resp.status_code == 200:
        models = [m["id"] for m in resp.json().get("data", [])]
        print("Available models in Proxy:")
        for m in sorted(models):
            print(f"  - {m}")
    else:
        print(f"Error fetching models: HTTP {resp.status_code} - {resp.text}")
except Exception as e:
    print(f"Connection error: {e}")
