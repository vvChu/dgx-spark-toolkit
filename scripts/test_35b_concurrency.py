import concurrent.futures
import requests
import time
import json
import sys

URL = "http://localhost:8004/v1/chat/completions"
MODEL = "qwen3.5-35b"
TIMEOUT = 300  # 5 minutes - enough for concurrent generation

PROMPTS = [
    "Write a short poem about the ocean.",
    "What is 2+2? Answer briefly.",
    "Explain gravity in one sentence.",
    "Name 3 programming languages.",
    "What color is the sky?",
    "Translate 'hello' to French.",
    "What is the capital of Japan?",
    "Write a haiku about rain.",
    "What does CPU stand for?",
    "Name a famous scientist.",
]

def fetch(prompt, idx):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 50,
        "temperature": 0.7
    }
    start_time = time.time()
    try:
        response = requests.post(URL, json=payload, timeout=TIMEOUT)
        result = response.json()
        duration = time.time() - start_time
        if response.status_code == 200 and "choices" in result:
            text = result["choices"][0]["message"]["content"][:60]
            print(f"[Req {idx}] ✅ {duration:.2f}s - {text}...")
        else:
            print(f"[Req {idx}] ❌ {duration:.2f}s - Status: {response.status_code}")
        return result
    except Exception as e:
        duration = time.time() - start_time
        print(f"[Req {idx}] ❌ {duration:.2f}s - Error: {e}")
        return None

def main(concurrency=5):
    print(f"\n{'='*60}")
    print(f"Concurrency Test: {concurrency} simultaneous requests")
    print(f"Model: {MODEL} | Timeout: {TIMEOUT}s | Max tokens: 50")
    print(f"{'='*60}\n")
    
    prompts_to_run = (PROMPTS * (concurrency // len(PROMPTS) + 1))[:concurrency]
    
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(fetch, prompt, i): i for i, prompt in enumerate(prompts_to_run)}
        results = []
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    total_time = time.time() - start
    
    success_count = sum(1 for r in results if r is not None and "choices" in r)
    print(f"\n{'='*60}")
    print(f"Results: {success_count}/{concurrency} successful")
    print(f"Total Time: {total_time:.2f}s")
    if success_count > 0:
        print(f"Avg Time/Req: {total_time/success_count:.2f}s")
    print(f"{'='*60}\n")
    
    return success_count == concurrency

if __name__ == "__main__":
    levels = [int(sys.argv[1])] if len(sys.argv) > 1 else [1, 5, 10, 20, 30]
    all_passed = True
    for level in levels:
        if not main(level):
            all_passed = False
            print(f"⚠️  Failed at concurrency level {level}, stopping.")
            break
        print(f"✅ Passed concurrency level {level}\n")
    
    if all_passed:
        print("🎉 All concurrency levels passed!")
