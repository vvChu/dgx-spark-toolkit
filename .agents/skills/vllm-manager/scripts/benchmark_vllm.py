"""
vLLM Benchmark Script — Measures TPS, latency, and throughput
for models served via vLLM's OpenAI-compatible API.
"""
import requests
import time
import argparse
import json


def benchmark_model(api_base: str, model_name: str, prompt: str, max_tokens: int = 100, runs: int = 3):
    """Run multiple inference passes and return average metrics."""
    url = f"{api_base}/v1/chat/completions"
    
    results = []
    for i in range(runs):
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "stream": False
        }
        
        try:
            start = time.time()
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            elapsed = time.time() - start
            
            data = resp.json()
            usage = data.get("usage", {})
            completion_tokens = usage.get("completion_tokens", 0)
            prompt_tokens = usage.get("prompt_tokens", 0)
            tps = completion_tokens / elapsed if elapsed > 0 else 0
            
            results.append({
                "run": i + 1,
                "tps": round(tps, 2),
                "latency": round(elapsed, 2),
                "completion_tokens": completion_tokens,
                "prompt_tokens": prompt_tokens,
                "text_preview": data["choices"][0]["message"]["content"][:100]
            })
            
            print(f"  Run {i+1}: {tps:.1f} TPS | {elapsed:.2f}s | {completion_tokens} tokens")
            
        except Exception as e:
            print(f"  Run {i+1}: ❌ Error: {e}")
            results.append({"run": i + 1, "tps": 0, "latency": 0, "error": str(e)})
    
    return results


def check_health(api_base: str):
    """Check if the vLLM server is responding."""
    try:
        resp = requests.get(f"{api_base}/v1/models", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        return [m["id"] for m in models]
    except Exception as e:
        return None


def main():
    parser = argparse.ArgumentParser(description="vLLM Benchmark Tool")
    parser.add_argument("--port", type=int, default=8004, help="vLLM server port")
    parser.add_argument("--host", type=str, default="localhost", help="vLLM server host")
    parser.add_argument("--model", type=str, default="rag-core", help="Model name")
    parser.add_argument("--runs", type=int, default=3, help="Number of benchmark runs")
    parser.add_argument("--max-tokens", type=int, default=100, help="Max tokens per response")
    parser.add_argument("--prompt", type=str, 
                        default="Explain the architecture of a transformer neural network in exactly 50 words.",
                        help="Benchmark prompt")
    args = parser.parse_args()
    
    api_base = f"http://{args.host}:{args.port}"
    
    print(f"🚀 vLLM BENCHMARK")
    print(f"   Server: {api_base}")
    print(f"   Model:  {args.model}")
    print(f"   Runs:   {args.runs}")
    print(f"{'='*50}\n")
    
    # Health check
    print("📡 Health Check...")
    models = check_health(api_base)
    if models is None:
        print(f"   ❌ Server at {api_base} is not responding!")
        return
    print(f"   ✅ Available models: {', '.join(models)}\n")
    
    # Run benchmark
    print(f"⏳ Running {args.runs} inference passes...")
    results = benchmark_model(api_base, args.model, args.prompt, args.max_tokens, args.runs)
    
    # Summary
    valid = [r for r in results if r.get("tps", 0) > 0]
    if valid:
        avg_tps = sum(r["tps"] for r in valid) / len(valid)
        avg_latency = sum(r["latency"] for r in valid) / len(valid)
        print(f"\n{'='*50}")
        print(f"📊 RESULTS: {args.model}")
        print(f"   Avg TPS:     {avg_tps:.1f} tokens/sec")
        print(f"   Avg Latency: {avg_latency:.2f}s")
        print(f"   Success:     {len(valid)}/{args.runs}")
        print(f"{'='*50}")
    else:
        print("\n❌ All runs failed!")


if __name__ == "__main__":
    main()
