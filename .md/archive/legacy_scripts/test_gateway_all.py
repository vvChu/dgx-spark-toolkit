import os
import yaml
import requests
import time
import concurrent.futures

env_path = "/home/vvc/Codebase/dgx-spark-toolkit/.env"
litellm_key = ""
with open(env_path, "r") as f:
    for line in f:
        if line.startswith("LITELLM_MASTER_KEY="):
            litellm_key = line.split("=", 1)[1].strip()
            break

config_path = "/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml"
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

# Extract unique model names
models = set()
for m in config.get("model_list", []):
    name = m.get("model_name")
    if name:
        models.add(name)
models = sorted(list(models))

endpoint = "http://localhost:8090/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {litellm_key}"
}

print(f"Testing {len(models)} models from litellm_config.yaml via Local AI Gateway...\n")

def test_model(model):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with 'OK' only."}],
        "max_tokens": 10
    }
    start = time.time()
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=40)
        latency = time.time() - start
        if resp.status_code == 200:
            return f"✅ {model}: OK ({latency:.2f}s)"
        else:
            return f"❌ {model}: Failed ({resp.status_code}) in {latency:.2f}s - {resp.text[:50]}"
    except Exception as e:
        latency = time.time() - start
        return f"❌ {model}: Error in {latency:.2f}s - {e}"

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    results = list(executor.map(test_model, models))

for r in results:
    print(r)
