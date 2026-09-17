import os
import requests
import time

# Load config from .env
env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
proxy_url = "http://100.79.241.120:8045/v1"
proxy_key = "sk-9a13a60d641a42f9a74b18d58d44a358"

if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GATEWAY_PROXY_URL="):
                proxy_url = line.split("=", 1)[1].strip()
                if proxy_url.endswith("/v1"):
                    pass
                elif proxy_url.endswith("/"):
                    proxy_url = proxy_url.rstrip("/")
            elif line.startswith("GATEWAY_PROXY_KEY="):
                proxy_key = line.split("=", 1)[1].strip()

# Base URL for native rest endpoint
native_base = proxy_url.replace("/v1", "")

models_to_test = [
    "gemini-3.5-flash-low",
    "gemini-3.5-flash-medium",
    "gemini-3.5-flash-high",
]

print(f"Proxy URL: {proxy_url}")
print(f"Proxy Key: {proxy_key[:10]}...{proxy_key[-5:] if len(proxy_key) > 10 else ''}")
print("--- 1. Testing via OpenAI /chat/completions endpoint ---")

for model in models_to_test:
    # We will try multiple formats to find what works
    formats = [
        model,
        f"openai/{model}",
        f"openai/vertex_ai/{model}"
    ]
    for fmt in formats:
        print(f"[*] Testing {fmt} ... ", end="", flush=True)
        payload = {
            "model": fmt,
            "messages": [{"role": "user", "content": "Reply 'Hello, connection OK.' in 5 words or less."}],
            "max_tokens": 15
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {proxy_key}"
        }
        start = time.time()
        try:
            resp = requests.post(f"{proxy_url}/chat/completions", headers=headers, json=payload, timeout=10)
            latency = time.time() - start
            if resp.status_code == 200:
                res_json = resp.json()
                reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                print(f"✅ SUCCESS ({latency:.2f}s) -> Reply: {reply}")
            else:
                print(f"❌ FAILED ({resp.status_code}) -> {resp.text[:120]}")
        except Exception as e:
            print(f"💥 ERROR -> {e}")

print("\n--- 2. Testing via Native Gemini /v1beta/models endpoint ---")
for model in models_to_test:
    # Try native REST format
    print(f"[*] Testing native REST for {model} ... ", end="", flush=True)
    url = f"{native_base}/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": proxy_key,
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{
            "parts": [{"text": "Reply 'Hello, connection OK.' in 5 words or less."}]
        }]
    }
    start = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        latency = time.time() - start
        if resp.status_code == 200:
            res_json = resp.json()
            try:
                reply = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            except Exception:
                reply = str(res_json)[:100]
            print(f"✅ SUCCESS ({latency:.2f}s) -> Reply: {reply}")
        else:
            print(f"❌ FAILED ({resp.status_code}) -> {resp.text[:120]}")
    except Exception as e:
        print(f"💥 ERROR -> {e}")
