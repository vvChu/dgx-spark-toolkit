import os
import urllib.request
import urllib.error
import json
import socket
import sys

API_KEY = os.getenv("GEMINI_API_KEY_2", "AIzaSyCbNn4eJWDhbvZwQJ6AQdapBcH1QmITAqY") # GEMINI_API_KEY_2 from .env
MODEL = "gemini-3.5-flash"

print(f"Testing direct Google Gemini API connection for model '{MODEL}'...")

# URL for Gemini API chat completion (using Google's native REST API)
url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

payload = {
    "contents": [{
        "parts": [{"text": "Hãy viết một bài thơ ngắn 2 câu về AI."}]
    }],
    "generationConfig": {
        "thinkingConfig": {
            "thinkingBudget": 1024
        }
    }
}

print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
req_data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(url, data=req_data)
req.add_header("Content-Type", "application/json")

try:
    with urllib.request.urlopen(req, timeout=30) as response:
        res_body = response.read().decode("utf-8")
        res_json = json.loads(res_body)
        
        print("✅ SUCCESS!")
        print(json.dumps(res_json, indent=2, ensure_ascii=False))
except urllib.error.HTTPError as e:
    print(f"❌ FAILED (HTTP {e.code}: {e.reason})")
    try:
        err_body = e.read().decode("utf-8")
        print(f"Error Details: {err_body}")
    except Exception:
        pass
except urllib.error.URLError as e:
    print(f"❌ FAILED (Connection error: {e.reason})")
except Exception as e:
    print(f"❌ FAILED ({e})")
