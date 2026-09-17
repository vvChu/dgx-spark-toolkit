import requests

GATEWAY_URL = "http://100.79.241.120:8045/v1/messages"
HEADERS = {
    "x-api-key": "sk-9a13a60d641a42f9a74b18d58d44a358",
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json"
}

payload = {
    "model": "claude-opus-4-5-thinking",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 1000
}

response = requests.post(GATEWAY_URL, headers=HEADERS, json=payload, timeout=10)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
