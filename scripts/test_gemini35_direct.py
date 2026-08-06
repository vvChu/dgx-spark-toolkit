import os
import requests
import json

# Read keys from .env
env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
keys = []
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GEMINI_API_KEY_"):
                parts = line.split("=", 1)
                val = parts[1].strip()
                if val and "placeholder" not in val:
                    keys.append((parts[0], val))

if not keys:
    print("No valid Gemini API keys found in .env!")
    exit(1)

# We will use the first active key found to test direct connection to Google
key_name, api_key = keys[0]
print(f"Testing direct connection to Google Gemini API using key: {key_name} ({api_key[:10]}...)\n")

levels = ["minimal", "low", "medium", "high"]
model = "gemini-3.5-flash"

for level in levels:
    print(f"[*] Testing {model} with thinking_level = '{level}' ... ", end="", flush=True)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{
            "parts": [{"text": "Reply with 'Gravity works.' and then list its mechanism in 2 sentences."}]
        }],
        "generationConfig": {
            "thinking_config": {
                "thinking_level": level
            }
        }
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            res_json = resp.json()
            candidate = res_json.get('candidates', [{}])[0]
            parts = candidate.get('content', {}).get('parts', [])
            
            text = ""
            has_thought = False
            thought_text = ""
            
            for p in parts:
                if 'text' in p:
                    text += p['text']
                if 'thought' in p or p.get('thoughtSignature') or 'thought' in str(p):
                    has_thought = True
                    thought_text = str(p)
            
            print(f"✅ SUCCESS")
            print(f"   [Reply]: {text.strip()}")
            if has_thought:
                print(f"   [Thinking structure detected]: Yes")
            else:
                print(f"   [Thinking structure detected]: No")
        else:
            print(f"❌ FAILED (HTTP {resp.status_code})")
            print(f"   Error: {resp.text[:250]}")
    except Exception as e:
        print(f"💥 ERROR: {e}")
    print()
