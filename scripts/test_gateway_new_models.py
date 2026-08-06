import requests
import json
import time

API_KEY = "sk-spark-secure-key-2026"
BASE_URL = "http://127.0.0.1:8090/v1"

print("=== TESTING NEWLY ADDED MODELS ON LOCAL AI GATEWAY ===\n")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 1. Test gemini-2.5-flash-lite
print("[*] Testing gemini-2.5-flash-lite (Chat) ...")
payload_chat = {
    "model": "gemini-2.5-flash-lite",
    "messages": [{"role": "user", "content": "Reply with 'Lite working.' and explain what a light version is in 1 sentence."}],
    "max_tokens": 50
}
start = time.time()
try:
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload_chat, timeout=20)
    latency = time.time() - start
    print(f"    Status Code: {resp.status_code}")
    if resp.status_code == 200:
        reply = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"    ✅ SUCCESS ({latency:.2f}s) -> Reply: {reply}")
    else:
        print(f"    ❌ FAILED -> {resp.text[:300]}")
except Exception as e:
    print(f"    💥 ERROR -> {e}")
print()

# 2. Test gemini-embedding-2
print("[*] Testing gemini-embedding-2 (Embedding) ...")
payload_embed = {
    "model": "gemini-embedding-2",
    "input": ["Tôi đang thử nghiệm Gemini Embedding 2."]
}
start = time.time()
try:
    resp = requests.post(f"{BASE_URL}/embeddings", headers=headers, json=payload_embed, timeout=20)
    latency = time.time() - start
    print(f"    Status Code: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        if data:
            emb = data[0].get("embedding", [])
            print(f"    ✅ SUCCESS ({latency:.2f}s) -> Received embedding length: {len(emb)}")
        else:
            print("    ❌ FAILED -> Response data is empty.")
    else:
        print(f"    ❌ FAILED -> {resp.text[:300]}")
except Exception as e:
    print(f"    💥 ERROR -> {e}")

print("\n=== INTEGRATION TEST OF NEW MODELS COMPLETE ===")
