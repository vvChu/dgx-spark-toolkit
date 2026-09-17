import requests

# The native Gemini REST endpoint path on the proxy
GATEWAY_URL = "http://100.79.241.120:8045/v1beta/models/gemini-3.1-flash-lite:generateContent"
HEADERS = {
    "x-goog-api-key": "sk-9a13a60d641a42f9a74b18d58d44a358",
    "Content-Type": "application/json"
}

payload = {
    "contents": [{
        "parts": [{"text": "Hello"}]
    }]
}

response = requests.post(GATEWAY_URL, headers=HEADERS, json=payload, timeout=20)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
