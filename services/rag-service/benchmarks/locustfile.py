import time
import random
import uuid
from locust import HttpUser, task, between, events
from typing import List, Dict
import os

# --- Configuration ---
AI_GATEWAY_URL = "/v1/chat/completions"
MODELS = ["qwen3.5-35b", "smartest-brain"]  # smartest-brain is the cloud fallback
SECURE_KEY = os.environ.get("LITELLM_MASTER_KEY", "")

# Test Queries (Realistic RAG scenarios)
QUERIES = [
    "Dựa trên tài liệu kỹ thuật, hãy hướng dẫn cách triển khai RAG trên NVIDIA GB10.",
    "Lợi ích của việc sử dụng FlashInfer trong vLLM là gì?",
    "Làm thế nào để tối ưu hóa VRAM cho model MoE 35B?",
    "Giải thích cơ chế Prefix Caching trong kiến trúc vLLM.",
    "So sánh hiệu năng giữa Blackwell GB10 và H100 cho tác vụ LLM Inference.",
    "Làm sao để cấu hình Semantic Cache trong LiteLLM?",
    "Báo cáo về tình trạng ổn định của hệ thống DGX Spark hiện tại.",
    "Kiến trúc MoE (Mixture of Experts) của Qwen 3.5 có gì đặc biệt?"
]


class RAGExtremeLoadTester(HttpUser):
    wait_time = between(1, 4)  # Realistic user pacing

    @task(3)
    def test_qwen_35b(self):
        self._test_chat("qwen3.5-35b")

    @task(1)
    def test_smart_fallback(self):
        self._test_chat("smartest-brain")

    def _test_chat(self, model_id: str):
        query = random.choice(QUERIES)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SECURE_KEY}"
        }
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": query}],
            "max_tokens": 512,
            "temperature": 0.3,
            "user": f"locust_user_{uuid.uuid4().hex[:8]}"
        }

        start_time = time.time()
        with self.client.post(AI_GATEWAY_URL, json=payload, headers=headers, name=f"Chat: {model_id}", catch_response=True) as response:
            duration = (time.time() - start_time) * 1000

            if response.status_code == 200:
                try:
                    res_json = response.json()
                    tokens = res_json.get("usage", {}).get("completion_tokens", 0)
                    cache_hit = "True" if response.headers.get("x-litellm-cache-hit") == "HIT" else "False"

                    # Custom metrics for reporting
                    events.request.fire(
                        request_type="AI_METRIC",
                        name=f"TokensPerSec:{model_id}",
                        response_time=duration,
                        response_length=tokens
                    )

                    if tokens > 0:
                        tps = tokens / (duration / 1000)
                        response.success()
                        # print(f"[{model_id}] {tps:.2f} tok/s | Cache: {cache_hit}")
                    else:
                        response.failure("Empty response body")
                except Exception as e:
                    response.failure(f"JSON Parse Error: {str(e)}")
            else:
                response.failure(f"HTTP {response.status_code}: {response.text}")


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--test-id", type=str, default="load_test_v5", help="Unique ID for this test run")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print(f"🚀 Starting Extreme RAG Load Test v5")
    print(f"🎯 Target: 100 Concurrent Users | Models: {MODELS}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print(f"🏁 Load Test Finished. Exporting results...")


# ── RAG Service Direct Testing ──────────────────────────────────────────
RAG_QUERIES = [
    "Quy chuẩn phòng cháy chữa cháy cho nhà cao tầng",
    "Quy định về an toàn lao động trong xây dựng",
    "Tiêu chuẩn BIM ISO 19650 áp dụng tại Việt Nam",
    "Nghị định 15/2021 về quản lý dự án đầu tư xây dựng",
    "Thông tư hướng dẫn quy hoạch xây dựng đô thị",
    "Quy chuẩn kỹ thuật quốc gia về thiết kế kết cấu thép",
]


class RAGServiceTester(HttpUser):
    """Load-test RAG service endpoints directly (not via AI Gateway).

    Usage:
        locust -f locustfile.py --host http://localhost:8005 RAGServiceTester
    """
    wait_time = between(0.5, 2)

    @task(5)
    def test_search(self):
        query = random.choice(RAG_QUERIES)
        with self.client.post(
            "/search",
            json={"query": query, "limit": 5, "use_hyde": False, "use_cache": True},
            name="RAG: /search",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                cached = data.get("cached", False)
                count = len(data.get("results", []))
                if cached:
                    events.request.fire(
                        request_type="RAG_METRIC", name="CacheHit:/search",
                        response_time=resp.elapsed.total_seconds() * 1000,
                        response_length=count,
                    )
                resp.success()
            elif resp.status_code == 429:
                resp.failure("Rate limited")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    def test_chat(self):
        query = random.choice(RAG_QUERIES)
        with self.client.post(
            "/chat",
            json={"query": query, "language": "vi"},
            name="RAG: /chat",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 429:
                resp.failure("Rate limited")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def test_chat_stream(self):
        query = random.choice(RAG_QUERIES)
        with self.client.post(
            "/chat/stream",
            json={"query": query, "language": "vi"},
            name="RAG: /chat/stream",
            catch_response=True,
            stream=True,
        ) as resp:
            if resp.status_code == 200:
                # Read the SSE stream
                full_content = ""
                for line in resp.iter_lines():
                    if line and line.startswith("data: "):
                        full_content += line[6:]
                        if "[DONE]" in line:
                            break
                resp.success()
            elif resp.status_code == 429:
                resp.failure("Rate limited")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def test_health(self):
        self.client.get("/health", name="RAG: /health")

