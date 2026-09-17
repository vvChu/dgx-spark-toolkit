import requests

GATEWAY_URL = "http://127.0.0.1:8090/v1/chat/completions"
HEADERS = {
    "Authorization": "Bearer sk-spark-secure-key-2026",
    "Content-Type": "application/json"
}

payload = {
    "model": "gemini-3.1-pro-high",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100,
    "presence_penalty": 0.5
}

response = requests.post(GATEWAY_URL, headers=HEADERS, json=payload, timeout=120)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
