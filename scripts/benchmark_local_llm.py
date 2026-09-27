#!/usr/bin/env python3
"""Asynchronous Concurrency Benchmark for Local LLM (Qwen 35B NVFP4) on DGX Spark.

Supports Dual-Mode execution:
- gateway (default): Routes via LiteLLM AI Gateway (:8090) to record telemetry in PostgreSQL.
- direct: Routes directly to vLLM server (:8004) for raw engine latency and concurrency measurement.
"""

import argparse
import asyncio
import os
import sys
import time
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI

DEFAULT_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://127.0.0.1:8090/v1")
DEFAULT_DIRECT_URL = os.environ.get("VLLM_DIRECT_URL", "http://localhost:8004/v1")
DEFAULT_GATEWAY_KEY = os.environ.get("AI_GATEWAY_API_KEY", "sk-spark-secure-key-2026")

PROMPT = (
    "Hãy viết một bài luận chi tiết khoảng 300 từ về lịch sử và sự phát triển của công nghệ "
    "trí tuệ nhân tạo, từ những năm 1950 cho đến kỷ nguyên của LLMs hiện tại. Phân tích các bước ngoặt quan trọng."
)


async def fetch_completion(client: AsyncOpenAI, model: str, req_id: int, prompt: str = PROMPT) -> Dict[str, Any]:
    """Execute a single streaming chat completion request and measure TTFT and TPS."""
    start_time = time.time()
    first_token_time: Optional[float] = None
    token_count = 0

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=512,
            temperature=0.7,
        )

        async for chunk in response:
            if first_token_time is None:
                first_token_time = time.time()
            if chunk.choices and chunk.choices[0].delta.content:
                token_count += 1

        end_time = time.time()

        ttft = (first_token_time - start_time) if first_token_time else 0
        total_time = end_time - start_time
        generation_time = (end_time - first_token_time) if first_token_time else 0
        tps = token_count / generation_time if generation_time > 0 else 0

        return {
            "req_id": req_id,
            "ttft": ttft,
            "total_time": total_time,
            "tokens": token_count,
            "tps": tps,
            "error": None,
        }
    except Exception as exc:
        return {
            "req_id": req_id,
            "error": str(exc),
        }


async def run_benchmark(client: AsyncOpenAI, model: str, concurrency: int, prompt: str = PROMPT) -> None:
    """Run concurrent benchmark requests and print aggregated statistics."""
    print(f"\n--- Bắt đầu Benchmark với Concurrency = {concurrency} ---")
    start_time = time.time()

    tasks = [fetch_completion(client, model, i, prompt=prompt) for i in range(concurrency)]
    results = await asyncio.gather(*tasks)

    end_time = time.time()
    total_benchmark_time = end_time - start_time

    successful_results = [r for r in results if not r.get("error")]
    errors = [r.get("error") for r in results if r.get("error")]

    if successful_results:
        avg_ttft = sum(r["ttft"] for r in successful_results) / len(successful_results)
        avg_tps = sum(r["tps"] for r in successful_results) / len(successful_results)
        total_tokens = sum(r["tokens"] for r in successful_results)
        system_tps = total_tokens / total_benchmark_time if total_benchmark_time > 0 else 0

        print(f"✅ Tổng số request thành công: {len(successful_results)}/{concurrency}")
        print(f"⏳ Thời gian hoàn thành toàn bộ: {total_benchmark_time:.2f}s")
        print(f"⚡ Average TTFT (Time To First Token): {avg_ttft:.2f}s")
        print(f"⚡ Average TPS per request: {avg_tps:.2f} tokens/s")
        print(f"🚀 System Total Throughput: {system_tps:.2f} tokens/s")

    if errors:
        print(f"❌ Có {len(errors)} lỗi xảy ra:")
        for err in errors:
            print(f" - {err}")


async def async_main() -> None:
    parser = argparse.ArgumentParser(
        description="Concurrency Benchmark for Local LLM on DGX Spark"
    )
    parser.add_argument(
        "--mode",
        choices=["gateway", "direct"],
        default="gateway",
        help="Benchmark mode: 'gateway' (:8090 with telemetry) or 'direct' (:8004 raw vLLM)",
    )
    parser.add_argument(
        "--model",
        default="qwen-local-primary",
        help="Model identifier to test (default: qwen-local-primary)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        default=[1, 4],
        help="Concurrency levels to test sequentially (default: 1 4)",
    )
    parser.add_argument(
        "--allow-cache",
        action="store_true",
        help="Allow LiteLLM response caching (default: False, cache is bypassed to measure raw throughput)",
    )
    args = parser.parse_args()

    if args.mode == "gateway":
        base_url = DEFAULT_GATEWAY_URL
        api_key = DEFAULT_GATEWAY_KEY
        cache_status = "Allowed" if args.allow_cache else "Bypassed (Live Nonce)"
        mode_label = f"AI Gateway (:8090) [Telemetry Logged to PostgreSQL | Cache: {cache_status}]"
    else:
        base_url = DEFAULT_DIRECT_URL
        api_key = "sk-unused"
        mode_label = f"Direct vLLM (:8004) [Raw Hardware Concurrency]"

    print(f"🚀 Khởi động Benchmark ({mode_label})")
    print(f"🎯 Base URL: {base_url} | Model: {args.model}")

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    for c in args.concurrency:
        prompt = PROMPT
        if not args.allow_cache:
            prompt = f"{PROMPT} [Benchmark Nonce: {int(time.time() * 1000)}]"
        await run_benchmark(client, args.model, c, prompt=prompt)
        await asyncio.sleep(1)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
