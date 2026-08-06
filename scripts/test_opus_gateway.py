import requests

GATEWAY_URL = "http://127.0.0.1:8090/v1/chat/completions"
HEADERS = {
    "Authorization": "Bearer sk-spark-secure-key-2026",
    "Content-Type": "application/json"
}

payload = {
    "model": "claude-opus-4-5-thinking",
    "messages": [{"role": "user", "content": "Hello"}],
    "presence_penalty": 0.5
}

response = requests.post(GATEWAY_URL, headers=HEADERS, json=payload, timeout=20)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
