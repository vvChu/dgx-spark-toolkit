import requests, time, json, sys

BASE_URL = "http://localhost:8004"
MODEL = "qwen3.5-35b"


def single_chat(prompt, max_tokens=256, temperature=0.7):
    """Use chat completions endpoint with thinking disabled for consistent benchmarking."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    start = time.time()
    resp = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload, timeout=300)
    elapsed = time.time() - start
    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text[:200]}")
        return None, elapsed
    data = resp.json()
    usage = data.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    return completion_tokens, elapsed


def benchmark(seqs, prompt, max_tokens=256):
    print(f"\n{'='*60}")
    print(f"Benchmark: {seqs} concurrent requests, max_tokens={max_tokens}")
    print(f"{'='*60}")
    from concurrent.futures import ThreadPoolExecutor, as_completed

    start_all = time.time()
    with ThreadPoolExecutor(max_workers=seqs) as executor:
        futures = [executor.submit(single_chat, prompt, max_tokens) for _ in range(seqs)]
        results = []
        for f in as_completed(futures):
            tokens, elapsed = f.result()
            results.append((tokens, elapsed))
    total_time = time.time() - start_all
    total_tokens = sum(t for t, _ in results if t)
    avg_latency = sum(e for _, e in results) / seqs
    tps = total_tokens / total_time if total_time > 0 else 0
    per_req_tps = sum(
        t / e for t, e in results if t and e > 0
    ) / len([1 for t, _ in results if t])

    print(f"  Total tokens generated: {total_tokens}")
    print(f"  Overall elapsed time:   {total_time:.2f}s")
    print(f"  Avg per-request latency:{avg_latency:.2f}s")
    print(f"  Aggregate throughput:   {tps:.1f} tokens/s")
    print(f"  Avg per-request speed:  {per_req_tps:.1f} tokens/s")
    return total_time, avg_latency, tps


if __name__ == "__main__":
    prompt = "Viết 3 câu giới thiệu về thành phố Hà Nội."

    # Warm-up request
    print("Warming up model...")
    tokens, elapsed = single_chat(prompt, max_tokens=64)
    if tokens:
        print(f"  Warm-up: {tokens} tokens in {elapsed:.2f}s ({tokens/elapsed:.1f} t/s)")
    else:
        print("  ⚠️  Warm-up failed! Check if model is running.")
        sys.exit(1)

    # Sequential benchmark (1 request)
    benchmark(1, prompt, max_tokens=256)
    # Moderate concurrency
    benchmark(5, prompt, max_tokens=256)
    # Higher concurrency
    benchmark(10, prompt, max_tokens=256)
