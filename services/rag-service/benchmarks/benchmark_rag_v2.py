import httpx
import time
import asyncio
import json

BASE_URL = "http://localhost:8000"

async def benchmark_search(query: str, use_hyde: bool, use_cache: bool):
    payload = {
        "query": query,
        "limit": 5,
        "use_reranker": True,
        "use_hyde": use_hyde,
        "use_cache": use_cache
    }
    
    start_time = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0) as client:
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

async def run_benchmark():
    print("--- Starting RAG v2 Benchmark (HyDE & Semantic Cache) ---")
    
    query = "Quy định về BIM trong Nghị định 15/2021"
    
    # 1. Cold Start (No Hyde, No Cache)
    print("\n1. Cold Start (Normal Search):")
    res1 = await benchmark_search(query, use_hyde=False, use_cache=False)
    print(json.dumps(res1, indent=2))
    
    # 2. HyDE Search
    print("\n2. HyDE Search (Enhanced Retrieval):")
    res2 = await benchmark_search(query, use_hyde=True, use_cache=False)
    print(json.dumps(res2, indent=2))
    
    # 3. Cache Miss (First time with cache enabled)
    print("\n3. Cache Miss (Cache enabled):")
    res3 = await benchmark_search(query, use_hyde=False, use_cache=True)
    print(json.dumps(res3, indent=2))
    
    # 4. Cache Hit (Repeat query)
    print("\n4. Cache Hit (Repeat query):")
    res4 = await benchmark_search(query, use_hyde=False, use_cache=True)
    print(json.dumps(res4, indent=2))

    # 5. Semantic Cache Hit (Slightly different wording)
    print("\n5. Semantic Cache Hit (Similar query):")
    query_sim = "BIM trong NĐ 15/2021 quy định thế nào?"
    res5 = await benchmark_search(query_sim, use_hyde=False, use_cache=True)
    print(json.dumps(res5, indent=2))

if __name__ == "__main__":
    asyncio.run(run_benchmark())
