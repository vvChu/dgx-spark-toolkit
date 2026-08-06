import os
import requests
import json
import time

API_KEY = "sk-spark-secure-key-2026"
BASE_URL = "http://127.0.0.1:8090/v1"  # AI Gateway external port is mapped to 8090 in docker-compose

print("=== STARTING AI GATEWAY AUTO-CORRECTION INTEGRATION TEST ===\n")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# ----------------------------------------------------------------------
# Test Case 1: Client calls Gemini 3.5 with ONLY thinking_budget (Gemini 2.x parameter)
# Expected: Auto-corrected to thinking_level='low', thinking_budget removed, returns 200 OK.
# ----------------------------------------------------------------------
print("[*] TEST CASE 1: Calling with thinking_budget=1024 (Gemini 2.x parameter) ...")
payload = {
    "model": "gemini-3.5-flash-medium",
    "messages": [{"role": "user", "content": "Reply 'OK' and explain gravity in 1 sentence."}],
    "thinking_budget": 1024,
    "max_tokens": 50
}
start = time.time()
try:
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=20)
    latency = time.time() - start
    print(f"    Status Code: {resp.status_code}")
    if resp.status_code == 200:
        res_json = resp.json()
        reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"    ✅ SUCCESS ({latency:.2f}s) -> Reply: {reply}")
    else:
        print(f"    ❌ FAILED -> {resp.text[:300]}")
except Exception as e:
    print(f"    💥 ERROR -> {e}")
print()

# ----------------------------------------------------------------------
# Test Case 2: Client calls with BOTH thinking_budget AND thinking_level
# Expected: thinking_budget removed to avoid hard 400 Bad Request error from Google, returns 200 OK.
# ----------------------------------------------------------------------
print("[*] TEST CASE 2: Calling with BOTH thinking_budget=2048 AND thinking_level='high' ...")
payload = {
    "model": "gemini-3.5-flash-high",
    "messages": [{"role": "user", "content": "Reply 'OK' and explain general relativity in 1 sentence."}],
    "thinking_budget": 2048,
    "thinking_level": "high",
    "max_tokens": 50
}
start = time.time()
try:
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=20)
    latency = time.time() - start
    print(f"    Status Code: {resp.status_code}")
    if resp.status_code == 200:
        res_json = resp.json()
        reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"    ✅ SUCCESS ({latency:.2f}s) -> Reply: {reply}")
    else:
        print(f"    ❌ FAILED -> {resp.text[:300]}")
except Exception as e:
    print(f"    💥 ERROR -> {e}")
print()

# ----------------------------------------------------------------------
# Test Case 3: Client calls with discouraged sampling parameters (temperature=1.0, top_p=1.0)
# Expected: Discouraged sampling parameters dropped, returns 200 OK.
# ----------------------------------------------------------------------
print("[*] TEST CASE 3: Calling with discouraged temperature=1.0 and top_p=1.0 ...")
payload = {
    "model": "gemini-3.5-flash-low",
    "messages": [{"role": "user", "content": "Reply 'OK' and explain spacetime curvature in 1 sentence."}],
    "temperature": 1.0,
    "top_p": 1.0,
    "max_tokens": 50
}
start = time.time()
try:
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=20)
    latency = time.time() - start
    print(f"    Status Code: {resp.status_code}")
    if resp.status_code == 200:
        res_json = resp.json()
        reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"    ✅ SUCCESS ({latency:.2f}s) -> Reply: {reply}")
    else:
        print(f"    ❌ FAILED -> {resp.text[:300]}")
except Exception as e:
    print(f"    💥 ERROR -> {e}")

print("\n=== AUTO-CORRECTION INTEGRATION TEST COMPLETE ===")
