import time
import requests

LITELLM_URL = "http://localhost:8090/v1/chat/completions"
LITELLM_KEY = "sk-spark-secure-key-2026"

models = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-thinking",
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "gemini-3.1-flash-lite"
]

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LITELLM_KEY}"
}

print("Testing models via AI Gateway (port 4000)...\n")

for m in models:
    payload = {
        "model": m,
        "messages": [{"role": "user", "content": "Say hello in 1 word"}],
        "max_tokens": 10
    }
    
    start_time = time.time()
    try:
        resp = requests.post(LITELLM_URL, json=payload, headers=headers, timeout=130)
        latency = time.time() - start_time
        
        if resp.status_code == 200:
            print(f"✅ {m}: OK ({latency:.2f}s) - Response: {resp.json()['choices'][0]['message']['content'].strip()}")
        else:
            print(f"❌ {m}: Failed ({resp.status_code}) in {latency:.2f}s - {resp.text[:100]}")
    except Exception as e:
        latency = time.time() - start_time
        print(f"❌ {m}: Error in {latency:.2f}s - {e}")
