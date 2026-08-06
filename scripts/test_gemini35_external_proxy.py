import os
import requests
import json
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
            elif line.startswith("GATEWAY_PROXY_KEY="):
                proxy_key = line.split("=", 1)[1].strip()

print("=== TESTING GEMINI 3.5 FLASH (LOW) DIRECTLY ON EXTERNAL API PROXY ===")
print(f"Target Proxy URL: {proxy_url}")
print(f"Target Model: gemini-3.5-flash-low\n")

headers = {
    "Authorization": f"Bearer {proxy_key}",
    "Content-Type": "application/json"
}

# Prompt requiring thinking
prompt = "Explain in 2 sentences why oil floats on water."

# Test Case 1: Standard call without parameters
print("[*] Test 1: Standard call (no special parameters)")
payload1 = {
    "model": "gemini-3.5-flash-low",
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": 100
}
try:
    start = time.time()
    resp = requests.post(f"{proxy_url}/chat/completions", headers=headers, json=payload1, timeout=15)
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

# Test Case 2: Call with thinking_level = "low"
print("[*] Test 2: Call with thinking_level = 'low'")
payload2 = {
    "model": "gemini-3.5-flash-low",
    "messages": [{"role": "user", "content": prompt}],
    "thinking_level": "low",
    "max_tokens": 100
}
try:
    start = time.time()
    resp = requests.post(f"{proxy_url}/chat/completions", headers=headers, json=payload2, timeout=15)
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

# Test Case 3: Call with thinking_budget = 1024
print("[*] Test 3: Call with thinking_budget = 1024")
payload3 = {
    "model": "gemini-3.5-flash-low",
    "messages": [{"role": "user", "content": prompt}],
    "thinking_budget": 1024,
    "max_tokens": 100
}
try:
    start = time.time()
    resp = requests.post(f"{proxy_url}/chat/completions", headers=headers, json=payload3, timeout=15)
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

# Test Case 4: Call with both inside extra_body/generationConfig (native style)
print("[*] Test 4: Call with generationConfig.thinking_config.thinking_level = 'low'")
payload4 = {
    "model": "gemini-3.5-flash-low",
    "messages": [{"role": "user", "content": prompt}],
    "extra_body": {
        "generationConfig": {
            "thinking_config": {
                "thinking_level": "low"
            }
        }
    },
    "max_tokens": 100
}
try:
    start = time.time()
    resp = requests.post(f"{proxy_url}/chat/completions", headers=headers, json=payload4, timeout=15)
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

print("\n=== EXTERNAL API PROXY COMPATIBILITY TEST COMPLETE ===")
