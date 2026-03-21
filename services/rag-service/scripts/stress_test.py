import httpx
import asyncio
import time
import statistics
import logging

import argparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8000/chat")
parser.add_argument("--samples", type=int, default=10)
parser.add_argument("--concurrency", type=int, default=2)
args = parser.parse_args()

URL = args.url
SAMPLES = args.samples
CONCURRENCY = args.concurrency

async def send_request(client, session_id):
    start = time.perf_counter()
    try:
        resp = await client.post(
            URL,
            json={"query": "EIR là gì?", "context_limit": 5},
            timeout=60.0
        )
        end = time.perf_counter()
        if resp.status_code == 200:
            return end - start
    except Exception as e:
        logger.error(f"Session {session_id} failed: {e}")
    return None

async def run_stress_test():
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(SAMPLES):
            tasks.append(send_request(client, i))
            if len(tasks) >= CONCURRENCY:
                results = await asyncio.gather(*tasks)
                tasks = []
        
        # remaining
        if tasks:
            results.extend(await asyncio.gather(*tasks))
            
    latencies = [r for r in results if r is not None]
    if not latencies:
        print("All requests failed.")
        return

    print("\n--- Stress Test Results ---")
    print(f"Total Requests: {SAMPLES}")
    print(f"Concurrency:    {CONCURRENCY}")
    print(f"Success Rate:   {len(latencies)/SAMPLES:.0%}")
    print(f"Avg Latency:    {statistics.mean(latencies):.2f}s")
    print(f"Max Latency:    {max(latencies):.2f}s")
    print(f"Min Latency:    {min(latencies):.2f}s")

if __name__ == "__main__":
    asyncio.run(run_stress_test())
