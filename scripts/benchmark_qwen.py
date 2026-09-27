#!/usr/bin/env python3
"""Benchmark script for Qwen 35B model on DGX Spark.

Supports Dual-Mode execution:
- gateway (default): Routes via LiteLLM AI Gateway (:8090) to record telemetry in PostgreSQL.
- direct: Routes directly to vLLM server (:8004) for raw engine latency measurement.
"""

import argparse
import json
import os
import sys
import time
import requests

GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://127.0.0.1:8090/v1/chat/completions")
DIRECT_URL = os.environ.get("VLLM_DIRECT_URL", "http://127.0.0.1:8004/v1/chat/completions")
GATEWAY_API_KEY = os.environ.get("AI_GATEWAY_API_KEY", "sk-spark-secure-key-2026")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Qwen 35B NVFP4 on DGX Spark")
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
        "--max-tokens",
        type=int,
        default=500,
        help="Maximum completion tokens to generate (default: 500)",
    )
    parser.add_argument(
        "--prompt",
        default="Viết một bài luận ngắn khoảng 300 chữ phân tích về tiềm năng của AI trong tương lai.",
        help="Custom prompt for benchmark",
    )
    parser.add_argument(
        "--allow-cache",
        action="store_true",
        help="Allow LiteLLM response caching (default: False, cache is bypassed to measure raw hardware throughput)",
    )
    args = parser.parse_args()

    # Append nonce to bypass response caching unless explicitly allowed
    prompt = args.prompt
    if not args.allow_cache:
        prompt = f"{args.prompt} [Benchmark Nonce: {int(time.time() * 1000)}]"

    if args.mode == "gateway":
        url = GATEWAY_URL
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GATEWAY_API_KEY}",
        }
        if not args.allow_cache:
            headers["Cache-Control"] = "no-cache"
        cache_status = "Allowed" if args.allow_cache else "Bypassed (Live Nonce)"
        mode_label = f"AI Gateway (:8090) [Telemetry Logged to PostgreSQL | Cache: {cache_status}]"
    else:
        url = DIRECT_URL
        headers = {"Content-Type": "application/json"}
        mode_label = f"Direct vLLM (:8004) [Raw Hardware Throughput]"

    data = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": args.max_tokens,
        "temperature": 0.7,
    }

    print(f"🚀 Gửi yêu cầu benchmark ({mode_label})...")
    print(f"🎯 URL: {url} | Model: {args.model}")

    try:
        start_time = time.time()
        response = requests.post(url, headers=headers, json=data, timeout=120)
        end_time = time.time()

        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            tokens = result["usage"]["completion_tokens"]
            duration = end_time - start_time
            speed = tokens / duration if duration > 0 else 0

            print("\n=== KẾT QUẢ BENCHMARK QWEN 35B ===")
            print(f"📍 Chế độ: {args.mode.upper()} ({url})")
            print(f"⏳ Thời gian tổng cộng: {duration:.2f} giây")
            print(f"📝 Số token sinh ra: {tokens} tokens")
            print(f"⚡ Tốc độ (Throughput): {speed:.2f} tokens/giây")
            print("-" * 40)
            print("Trích dẫn phản hồi:")
            print(f"{content[:200]}...")
        else:
            print(f"❌ Lỗi từ server: HTTP {response.status_code} - {response.text}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"❌ Lỗi: Không thể kết nối tới {url}. Vui lòng kiểm tra dịch vụ tương ứng.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
