import os
from litellm import completion

# Load env vars
env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
os.environ["GATEWAY_PROXY_URL"] = "http://100.79.241.120:8045/v1"
with open(env_path, "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("GATEWAY_PROXY_KEY="):
            os.environ["GATEWAY_PROXY_KEY"] = line.split("=", 1)[1].strip()
            break

print("Testing with openai/ prefix...")
try:
    response = completion(
        model="openai/gemini-2.5-flash-thinking",
        api_base=os.environ["GATEWAY_PROXY_URL"],
        api_key=os.environ["GATEWAY_PROXY_KEY"],
        messages=[{"role": "user", "content": "Hello"}]
    )
    print("OpenAI format success:", response.choices[0].message.content)
except Exception as e:
    print("OpenAI format failed:", e)

print("\nTesting with vertex_ai/ prefix...")
try:
    response = completion(
        model="vertex_ai/gemini-2.5-flash-thinking",
        api_base=os.environ["GATEWAY_PROXY_URL"],
        api_key=os.environ["GATEWAY_PROXY_KEY"],
        messages=[{"role": "user", "content": "Hello"}]
    )
    print("Vertex format success:", response.choices[0].message.content)
except Exception as e:
    print("Vertex format failed:", e)

print("\nTesting with vertex_ai/ prefix without /v1...")
try:
    response = completion(
        model="vertex_ai/gemini-2.5-flash-thinking",
        api_base="http://100.79.241.120:8045",
        api_key=os.environ["GATEWAY_PROXY_KEY"],
        messages=[{"role": "user", "content": "Hello"}]
    )
    print("Vertex format without /v1 success:", response.choices[0].message.content)
except Exception as e:
    print("Vertex format without /v1 failed:", e)
