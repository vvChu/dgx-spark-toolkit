import asyncio
import time
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="http://localhost:8004/v1",
    api_key="sk-unused",
)

MODEL = "qwen-local-primary"
PROMPT = "Hãy viết một bài luận chi tiết khoảng 500 từ về lịch sử và sự phát triển của công nghệ trí tuệ nhân tạo, từ những năm 1950 cho đến kỷ nguyên của LLMs hiện tại. Phân tích các bước ngoặt quan trọng."

async def fetch_completion(req_id):
    start_time = time.time()
    first_token_time = None
    token_count = 0
    
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT}],
            stream=True,
            max_tokens=1024,
            temperature=0.7
        )
        
        async for chunk in response:
            if first_token_time is None:
                first_token_time = time.time()
            if chunk.choices and chunk.choices[0].delta.content:
                # Approximation: length of text chunk roughly relates to tokens.
                # In streaming, typically each chunk is 1 token.
                token_count += 1
                
        end_time = time.time()
        
        ttft = first_token_time - start_time if first_token_time else 0
        total_time = end_time - start_time
        generation_time = end_time - first_token_time if first_token_time else 0
        tps = token_count / generation_time if generation_time > 0 else 0
        
        return {
            "req_id": req_id,
            "ttft": ttft,
            "total_time": total_time,
            "tokens": token_count,
            "tps": tps,
            "error": None
        }
    except Exception as e:
        return {
            "req_id": req_id,
            "error": str(e)
        }

async def run_benchmark(concurrency):
    print(f"\n--- Bắt đầu Benchmark với Concurrency = {concurrency} ---")
    start_time = time.time()
    
    tasks = [fetch_completion(i) for i in range(concurrency)]
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    total_benchmark_time = end_time - start_time
    
    successful_results = [r for r in results if not r.get("error")]
    errors = [r.get("error") for r in results if r.get("error")]
    
    if successful_results:
        avg_ttft = sum(r["ttft"] for r in successful_results) / len(successful_results)
        avg_tps = sum(r["tps"] for r in successful_results) / len(successful_results)
        total_tokens = sum(r["tokens"] for r in successful_results)
        system_tps = total_tokens / total_benchmark_time
        
        print(f"Tổng số request thành công: {len(successful_results)}/{concurrency}")
        print(f"Thời gian hoàn thành toàn bộ: {total_benchmark_time:.2f}s")
        print(f"Average TTFT (Time To First Token): {avg_ttft:.2f}s")
        print(f"Average TPS per request: {avg_tps:.2f} tokens/s")
        print(f"System Total Throughput: {system_tps:.2f} tokens/s")
    
    if errors:
        print(f"Có {len(errors)} lỗi xảy ra:")
        for err in errors:
            print(f" - {err}")

async def main():
    print("Khởi động quá trình Benchmark Model Qwen3.6-35B NVFP4 (MARLIN Backend)...")
    await run_benchmark(concurrency=1)
    await asyncio.sleep(2)
    await run_benchmark(concurrency=5)

if __name__ == "__main__":
    asyncio.run(main())
