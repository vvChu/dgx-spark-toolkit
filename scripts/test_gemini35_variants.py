import os
import requests
import json

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

native_base = proxy_url.replace("/v1", "")

# Let's test gemini-3.5-flash directly
test_models = ["gemini-3.5-flash", "gemini-3-flash"]

print("--- 1. Testing gemini-3.5-flash directly via OpenAI format ---")
for model in test_models:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply 'OK'"}],
        "max_tokens": 10
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {proxy_key}"
    }
    try:
        resp = requests.post(f"{proxy_url}/chat/completions", headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"✅ OpenAI format for {model}: Working (200) -> {resp.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip()}")
        else:
            print(f"❌ OpenAI format for {model}: Failed ({resp.status_code}) -> {resp.text[:200]}")
    except Exception as e:
        print(f"💥 OpenAI format for {model}: Error -> {e}")

print("\n--- 2. Testing gemini-3.5-flash directly via Native REST ---")
for model in test_models:
    url = f"{native_base}/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": proxy_key,
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{
            "parts": [{"text": "Reply 'OK'"}]
        }]
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            res_json = resp.json()
            try:
                reply = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            except:
                reply = str(res_json)[:100]
            print(f"✅ Native REST for {model}: Working (200) -> {reply}")
        else:
            print(f"❌ Native REST for {model}: Failed ({resp.status_code}) -> {resp.text[:200]}")
    except Exception as e:
        print(f"💥 Native REST for {model}: Error -> {e}")

print("\n--- 3. Testing with thinking_level configurations in Native REST ---")
for level in ["minimal", "low", "medium", "high"]:
    url = f"{native_base}/v1beta/models/gemini-3.5-flash:generateContent"
    headers = {
        "x-goog-api-key": proxy_key,
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{
            "parts": [{"text": "Explain why gravity holds things in 3 sentences."}]
        }],
        "generationConfig": {
            "thinking_config": {
                "thinking_level": level
            }
        }
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            res_json = resp.json()
            # Try to see if there is a thought process returned
            candidate = res_json.get('candidates', [{}])[0]
            parts = candidate.get('content', {}).get('parts', [])
            text = ""
            thought = ""
            for p in parts:
                if 'text' in p:
                    text += p['text']
                if 'thought' in p or p.get('thoughtSignature') or 'thought' in str(p):
                    thought += str(p)
            print(f"✅ thinking_level = {level}: Success! Response starts with: {text.strip()[:60]}...")
            if thought:
                print(f"   [Thoughts found]: {thought[:100]}...")
        else:
            print(f"❌ thinking_level = {level}: Failed ({resp.status_code}) -> {resp.text[:200]}")
    except Exception as e:
        print(f"💥 thinking_level = {level}: Error -> {e}")
