import requests
import json
import time

API_KEY = "sk-spark-secure-key-2026"
BASE_URL = "http://127.0.0.1:8090/v1"

print("=== TESTING GEMINI 3.5 FLASH VIA LOCAL API GATEWAY WITH PARAMETER AUTO-CORRECTION ===\n")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Prompt demanding reasoning
prompt = "If we have a bucket of 5 liters and a bucket of 3 liters, how do we measure exactly 4 liters? Explain step by step."

# We will send a request with BOTH the old 'thinking_budget' and discouraged 'temperature'
payload = {
    "model": "gemini-3.5-flash-medium",
    "messages": [{"role": "user", "content": prompt}],
    "thinking_budget": 4096,     # Old parameter that usually causes 400 Bad Request
    "temperature": 1.0,          # Discouraged parameter
    "max_tokens": 800
}

print(f"[*] Sending prompt: '{prompt}'")
print(f"[*] Parameters passed by client:")
print(f"    - model: gemini-3.5-flash-medium")
print(f"    - thinking_budget: 4096")
print(f"    - temperature: 1.0")
print("[*] Dispatching request...")

start = time.time()
try:
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=30)
    latency = time.time() - start
    print(f"\n[+] Gateway Response Status Code: {resp.status_code}")
    if resp.status_code == 200:
        res_json = resp.json()
        reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"✅ SUCCESS ({latency:.2f}s)")
        print("\n=== Model Response (Step-by-step Reasoning Output) ===")
        print(reply)
        print("======================================================")
        
        # Check usage tokens
        usage = res_json.get("usage", {})
        print(f"\n[*] Usage Stats:")
        print(f"    - Prompt Tokens: {usage.get('prompt_tokens')}")
        print(f"    - Completion Tokens: {usage.get('completion_tokens')}")
        print(f"    - Total Tokens: {usage.get('total_tokens')}")
    else:
        print(f"❌ FAILED -> {resp.text[:500]}")
except Exception as e:
    print(f"💥 ERROR -> {e}")

print("\n=== INTEGRATION TEST COMPLETE ===")
