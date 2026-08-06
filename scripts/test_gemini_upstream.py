import requests

GATEWAY_URL = "http://100.79.241.120:8045/v1/chat/completions"
HEADERS = {
    "Authorization": "Bearer sk-9a13a60d641a42f9a74b18d58d44a358",
    "Content-Type": "application/json"
}

payload = {
    "model": "gemini-3.1-flash-lite",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
}

response = requests.post(GATEWAY_URL, headers=HEADERS, json=payload, timeout=20)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
