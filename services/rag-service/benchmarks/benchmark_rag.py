import httpx
import time
import asyncio
import json

BASE_URL = "http://127.0.0.1:8005"


async def benchmark_search(query: str, use_hyde: bool, use_cache: bool, retries=5):
    payload = {
        "query": query,
        "limit": 5,
        "use_reranker": True,
        "use_hyde": use_hyde,
        "use_cache": use_cache
    }

    for i in range(retries):
        try:
            start_time = time.perf_counter()
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(f"{BASE_URL}/search", json=payload)
            end_time = time.perf_counter()

            latency = end_time - start_time
            status = resp.status_code
            data = resp.json() if status == 200 else {}
            cached = data.get("cached", False)

            return {
                "query": query,
                "hyde": use_hyde,
                "cache_enabled": use_cache,
                "latency_sec": latency,
                "status": status,
                "cached": cached,
                "results_count": len(data.get("results", []))
            }
        except httpx.ConnectError:
            print(f"Connection failed, retrying in 10s... ({i+1}/{retries})")
            await asyncio.sleep(10)

    raise Exception("Max retries reached")


async def run_benchmark():
    print("--- Starting RAG v3 Benchmark (Optimized Fast Cache) ---")

    query = "Quy định về BIM trong Nghị định 15/2021"

    # 1. Cold Start
    print("\n1. Cold Start (Normal Search):")
    res1 = await benchmark_search(query, use_hyde=False, use_cache=False)
    print(json.dumps(res1, indent=2))

    # 2. HyDE Search
    print("\n2. HyDE Search:")
    res2 = await benchmark_search(query, use_hyde=True, use_cache=False)
    print(json.dumps(res2, indent=2))

    # 3. Cache Hit (Exact query - Fast Path)
    print("\n3. Fast Cache Hit (Exact same query):")
    res3 = await benchmark_search(query, use_hyde=False, use_cache=True)
    print(json.dumps(res3, indent=2))

    # 4. Semantic Cache Hit (Similar query - Post-Rewrite Path)
    print("\n4. Semantic Cache Hit (Similar query):")
    query_sim = "BIM trong NĐ 15/2021 quy định thế nào?"
    res4 = await benchmark_search(query_sim, use_hyde=False, use_cache=True)
    print(json.dumps(res4, indent=2))

if __name__ == "__main__":
    asyncio.run(run_benchmark())
