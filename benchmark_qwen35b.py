import requests, time, json, sys

BASE_URL = "http://localhost:8004"
MODEL = "qwen3.5-35b"

def single_run(prompt, max_tokens=512, temperature=0.7):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    start = time.time()
    resp = requests.post(f"{BASE_URL}/v1/completions", json=payload, timeout=300)
    elapsed = time.time() - start
    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text}")
        return None, elapsed
    data = resp.json()
    # token count approximation: count words? vLLM returns usage if enabled
    usage = data.get("usage", {})
    total_tokens = usage.get("total_tokens")
    if total_tokens is None:
        # fallback: approximate by length of generated text split by spaces
        total_tokens = len(data.get("choices", [{}])[0].get("text", "").split())
    return total_tokens, elapsed

def benchmark(seqs, prompt, max_tokens=512):
    print(f"Running benchmark: {seqs} concurrent requests, max_tokens={max_tokens}")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    start_all = time.time()
    with ThreadPoolExecutor(max_workers=seqs) as executor:
        futures = [executor.submit(single_run, prompt, max_tokens) for _ in range(seqs)]
        results = []
        for f in as_completed(futures):
            tokens, elapsed = f.result()
            results.append((tokens, elapsed))
    total_time = time.time() - start_all
    total_tokens = sum(t for t, _ in results if t)
    avg_latency = sum(e for _, e in results) / seqs
    tps = total_tokens / total_time if total_time > 0 else 0
    print(f"Total tokens generated: {total_tokens}")
    print(f"Overall elapsed time: {total_time:.2f}s")
    print(f"Average per-request latency: {avg_latency:.2f}s")
    print(f"Throughput (tokens/s): {tps:.2f}")
    return total_time, avg_latency, tps

if __name__ == "__main__":
    # Simple prompt that triggers reasoning but not too long
    prompt = "Explain the theory of relativity in two sentences."
    # Warm‑up request (JIT compilation)
    print("Warming up model (JIT compilation)...")
    _ = single_run(prompt, max_tokens=64)
    # Sequential benchmark (1 request)
    benchmark(1, prompt, max_tokens=256)
    # Moderate concurrency
    benchmark(5, prompt, max_tokens=256)
    # Higher concurrency
    benchmark(10, prompt, max_tokens=256)
    # Max concurrency we tested earlier (20)
    benchmark(20, prompt, max_tokens=256)
