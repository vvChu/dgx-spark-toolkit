import asyncio
import aiohttp
import time
import json
import random

BASE_URL = "http://localhost:8004/v1"
MODEL = "qwen3.5-35b"

# Mixture of requests:
# 1. Short completion
# 2. JSON structured extraction
# 3. Streaming long completion
# 4. Long context summary

async def make_short_request(session, req_id):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": f"Explain what a proxy server is in one sentence. (ID: {req_id})"}],
        "max_tokens": 100,
        "temperature": 0.5
    }
    start = time.time()
    try:
        async with session.post(f"{BASE_URL}/chat/completions", json=payload, timeout=60) as resp:
            data = await resp.json()
            return "short", time.time() - start, True
    except Exception as e:
        print(f"Short error: {e}")
        return "short", time.time() - start, False

async def make_json_request(session, req_id):
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "company",
            "schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "year": {"type": "integer"}},
                "required": ["name", "year"]
            }
        }
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": f"OpenAI was founded in 2015. (Req {req_id})"}],
        "response_format": schema,
        "max_tokens": 50,
        "temperature": 0.1
    }
    start = time.time()
    try:
        async with session.post(f"{BASE_URL}/chat/completions", json=payload, timeout=60) as resp:
            data = await resp.json()
            content = data['choices'][0]['message']['content']
            if content.startswith("```json"):
                content = content[7:-3]
            res = json.loads(content.strip())
            if "OpenAI" in res.get("name", ""):
                 return "json", time.time() - start, True
            print(f"JSON Output mismatch: {res}")
            return "json", time.time() - start, False
    except Exception as e:
        print(f"JSON error: {e}")
        return "json", time.time() - start, False

async def make_streaming_request(session, req_id):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": f"Write a paragraph about space exploration. (ID: {req_id})"}],
        "max_tokens": 200,
        "stream": True,
        "temperature": 0.7
    }
    start = time.time()
    try:
        async with session.post(f"{BASE_URL}/chat/completions", json=payload, timeout=300) as resp:
            first_token_time = None
            async for line in resp.content:
                if line and first_token_time is None:
                    first_token_time = time.time()
            return "stream", time.time() - start, True
    except Exception as e:
        print(f"Stream error: {e}")
        return "stream", time.time() - start, False

async def worker(session, worker_id, end_time):
    results = []
    req_counts = 0
    while time.time() < end_time:
        choice = random.choice([make_short_request, make_json_request, make_streaming_request])
        res_type, latency, success = await choice(session, f"w{worker_id}_{req_counts}")
        results.append((res_type, latency, success))
        req_counts += 1
        # Add a tiny sleep to prevent flooding
        await asyncio.sleep(random.uniform(0.1, 0.5))
    return results

async def run_stress_test(duration=60, concurrency=20):
    print(f"--- [4] Starting Mixed Concurrency Stress Test ---")
    print(f"Duration: {duration}s | Concurrent Workers: {concurrency}")
    
    end_time = time.time() + duration
    async with aiohttp.ClientSession() as session:
        tasks = [worker(session, i, end_time) for i in range(concurrency)]
        all_results = await asyncio.gather(*tasks)
    
    flat_results = [item for sublist in all_results for item in sublist]
    total_reqs = len(flat_results)
    success_reqs = sum(1 for r in flat_results if r[2])
    
    print("\n--- Results ---")
    print(f"Total Requests Processed: {total_reqs}")
    print(f"Successful Requests: {success_reqs}")
    print(f"Failed Requests: {total_reqs - success_reqs}")
    print(f"Success Rate: {(success_reqs/total_reqs)*100 if total_reqs > 0 else 0:.1f}%")
    
    # Latency by type
    by_type = {}
    for r in flat_results:
        if r[2]: # only successful
            by_type.setdefault(r[0], []).append(r[1])
            
    for t, latencies in by_type.items():
        avg = sum(latencies) / len(latencies)
        print(f"Avg Latency ({t}): {avg:.2f}s (Count: {len(latencies)})")

if __name__ == "__main__":
    asyncio.run(run_stress_test(duration=60, concurrency=30))
