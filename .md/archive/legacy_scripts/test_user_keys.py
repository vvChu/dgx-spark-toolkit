import urllib.request
import urllib.error
import json

key = "AIzaSyA0JmWctaiv1tDbR_uT4CIOMop20brpEaA"

print(f"=== COMPREHENSIVE VERIFICATION FOR KEY '{key[:10]}...{key[-5:]}' ===\n")

# Test 1: Chat Completion / GenerateContent
print("[*] Test 1: Testing Chat Completion (gemini-2.5-flash)...")
url_chat = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
payload_chat = json.dumps({
    "contents": [{"parts": [{"text": "Reply with 'OK'."}]}]
}).encode("utf-8")

req_chat = urllib.request.Request(
    url_chat,
    data=payload_chat,
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req_chat, timeout=10) as response:
        res_body = response.read().decode("utf-8")
        res_json = json.loads(res_body)
        text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        print(f"  ✅ SUCCESS! Chat works -> Response: '{text}'")
except urllib.error.HTTPError as e:
    err_msg = ""
    try:
        err_msg = e.read().decode("utf-8")
        err_json = json.loads(err_msg)
        err_msg = err_json.get("error", {}).get("message", err_msg)
    except Exception:
        pass
    print(f"  ❌ Chat failed (HTTP {e.code}: {e.reason}) -> {err_msg[:180]}")
except Exception as e:
    print(f"  ❌ Chat error ({e})")

# Test 2: Embedding / EmbedContent
print("\n[*] Test 2: Testing Embedding (gemini-embedding-2)...")
url_embed = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={key}"
payload_embed = json.dumps({
    "content": {"parts": [{"text": "Kiểm tra kết nối."}]}
}).encode("utf-8")

req_embed = urllib.request.Request(
    url_embed,
    data=payload_embed,
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req_embed, timeout=10) as response:
        res_body = response.read().decode("utf-8")
        res_json = json.loads(res_body)
        embedding = res_json.get("embedding", {}).get("values", [])
        if embedding:
            print(f"  ✅ SUCCESS! Embedding works -> Vector length: {len(embedding)}")
except urllib.error.HTTPError as e:
    err_msg = ""
    try:
        err_msg = e.read().decode("utf-8")
        err_json = json.loads(err_msg)
        err_msg = err_json.get("error", {}).get("message", err_msg)
    except Exception:
        pass
    print(f"  ❌ Embedding failed (HTTP {e.code}: {e.reason}) -> {err_msg[:180]}")
except Exception as e:
    print(f"  ❌ Embedding error ({e})")
