import time
import requests
import concurrent.futures

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

print("Testing models via AI Gateway (port 8090) concurrently...\n")

def test_model(model):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 10
    }
    start_time = time.time()
    try:
        resp = requests.post(LITELLM_URL, json=payload, headers=headers, timeout=130)
        latency = time.time() - start_time
        if resp.status_code == 200:
            return f"✅ {model}: OK ({latency:.2f}s) - Response: {resp.json()['choices'][0]['message']['content'].strip()}"
        else:
            return f"❌ {model}: Failed ({resp.status_code}) in {latency:.2f}s - {resp.text[:100]}"
    except Exception as e:
        latency = time.time() - start_time
        return f"❌ {model}: Error in {latency:.2f}s - {e}"

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(test_model, m): m for m in models}
    for future in concurrent.futures.as_completed(futures):
        print(future.result())
