import os
import requests
import time
import json

env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
proxy_url = ""
proxy_key = ""
with open(env_path, "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("GATEWAY_PROXY_URL="):
            proxy_url = line.split("=", 1)[1].strip()
        elif line.startswith("GATEWAY_PROXY_KEY="):
            proxy_key = line.split("=", 1)[1].strip()

models_to_test = [
    "gemini-3.1-pro-low",
    "gemini-2.5-pro",
    "claude-opus-4-6-thinking",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-agent",
    "gemini-3-flash",
    "gemini-pro-agent",
    "gemini-2.5-flash-thinking",
    "gemini-3.1-pro-high",
    "gemini-3.1-flash-lite",
    "gpt-oss-120b-medium",
    "gemini-2.5-flash",
    "gemini-3.1-flash-image",
    "claude-sonnet-4-6",
    "gemini-3-pro-image"
]

print("Testing all Proxy Models comprehensively...\n")

def test_openai(model_id):
    endpoint = f"{proxy_url}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {proxy_key}"}
    payload = {"model": model_id, "messages": [{"role": "user", "content": "Reply 'OK'"}], "max_tokens": 10}
    try:
        start = time.time()
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=10)
        return resp.status_code, time.time() - start, resp.text[:50]
    except Exception as e:
        return 0, 0, str(e)

for m in models_to_test:
    print(f"--- Testing {m} ---")
    if "claude" in m:
        # Test anthropic endpoint
        endpoint = f"{proxy_url}/messages" # or maybe proxy_url expects /v1/messages. LiteLLM proxy usually uses /chat/completions even for Claude if using OpenAI SDK. But let's test OpenAI format first.
        code, lat, err = test_openai(m)
        print(f"  [OpenAI format]: {code} in {lat:.2f}s")
    else:
        # Test standard
        code1, lat1, err1 = test_openai(m)
        print(f"  [Standard]: {code1} in {lat1:.2f}s - {err1 if code1 != 200 else ''}")
        if code1 in [400, 503]:
            # Test vertex_ai prefix
            code2, lat2, err2 = test_openai(f"vertex_ai/{m}")
            print(f"  [Vertex AI prefix]: {code2} in {lat2:.2f}s - {err2 if code2 != 200 else ''}")
