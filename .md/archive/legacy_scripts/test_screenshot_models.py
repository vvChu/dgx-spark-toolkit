import os
import requests
import time
import concurrent.futures

env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
litellm_key = ""
with open(env_path, "r") as f:
    for line in f:
        if line.startswith("LITELLM_MASTER_KEY="):
            litellm_key = line.split("=", 1)[1].strip()
            break

models = [
    "gemini-3.1-flash-lite", 
    "claude-opus-4-6-thinking", 
    "gemini-3-flash", 
    "claude-sonnet-4-6", 
    "gemini-3.1-pro-high", 
    "gemini-2.5-pro", 
    "gemini-3.1-flash-image", 
    "gemini-2.5-flash-thinking", 
    "gemini-2.5-flash-lite", 
    "gemini-2.5-flash", 
    "gpt-oss-120b-medium", 
    "gemini-pro-agent", 
    "gemini-3.1-pro-low", 
    "gemini-3-pro-image"
]

endpoint = "http://localhost:8090/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {litellm_key}"
}

print(f"Testing {len(models)} models from screenshot via Local AI Gateway...\n")

def test_model(model):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply 'OK'"}],
        "max_tokens": 10
    }
    start = time.time()
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=25)
        latency = time.time() - start
        if resp.status_code == 200:
            print(f"✅ {model}: OK ({latency:.2f}s)")
        else:
            print(f"❌ {model}: Failed ({resp.status_code}) in {latency:.2f}s - {resp.text[:50]}")
    except Exception as e:
        latency = time.time() - start
        print(f"❌ {model}: Error in {latency:.2f}s - {e}")

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    executor.map(test_model, models)
