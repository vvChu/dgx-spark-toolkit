"""
vLLM Health Monitor — Checks the status of all vLLM containers
and reports GPU memory, model availability, and key metrics.
"""
import subprocess
import requests
import json
import sys
import os

# Add shared module to path
current_dir = os.path.dirname(os.path.abspath(__file__))
skills_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(os.path.join(skills_dir, "shared"))

from vllm_client import VLLM_API_BASE, GATEWAY_API_KEY, chat_completion

VLLM_ENDPOINTS = [
    {"name": "Qwen 3.5 35B", "port": 8004, "container": "qwen36b"},
]


def check_docker_status(container_name: str) -> str:
    """Check if a Docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "not found"
    except Exception:
        return "error"


def check_model_ready(port: int) -> dict:
    """Check if the vLLM server is serving models."""
    try:
        resp = requests.get(f"http://localhost:{port}/v1/models", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        return {"ready": True, "models": [m["id"] for m in models]}
    except Exception:
        return {"ready": False, "models": []}


def get_vllm_metrics(port: int) -> dict:
    """Fetch key Prometheus metrics from vLLM."""
    try:
        resp = requests.get(f"http://localhost:{port}/metrics", timeout=5)
        resp.raise_for_status()
        text = resp.text
        
        metrics = {}
        for line in text.split("\n"):
            if line.startswith("#"):
                continue
            for key in ["vllm:num_requests_running", "vllm:num_requests_waiting", 
                        "vllm:gpu_cache_usage_perc", "vllm:avg_generation_throughput_toks_per_s"]:
                if line.startswith(key):
                    parts = line.split(" ")
                    if len(parts) >= 2:
                        metrics[key.replace("vllm:", "")] = parts[-1]
        return metrics
    except Exception:
        return {}


def get_gpu_info() -> str:
    """Get GPU memory utilization via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 3:
                return f"{parts[0]}MB / {parts[1]}MB ({parts[2]}% GPU util)"
        return "unavailable"
    except Exception:
        return "unavailable"


def get_gateway_health() -> str:
    """Check AI Gateway health using the shared vllm_client."""
    try:
        response = chat_completion(
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            model="claude-sonnet-4-6"
        )
        return f"✅ OK (Response: {response.strip()[:15]}...)"
    except Exception as e:
        return f"❌ FAILED ({str(e)})"


def main():
    print("🖥️  vLLM & GATEWAY HEALTH MONITOR — DGX Spark")
    print("=" * 55)
    
    # GPU Status
    gpu_info = get_gpu_info()
    print(f"\n🎮 GPU Memory: {gpu_info}")
    
    # AI Gateway Status (Using shared module)
    print(f"\n🌐 AI Gateway ({VLLM_API_BASE}):")
    print(f"   Status: {get_gateway_health()}")
    
    # Per-endpoint status
    for ep in VLLM_ENDPOINTS:
        print(f"\n{'─'*55}")
        print(f"📦 {ep['name']} (port {ep['port']}, container: {ep['container']})")
        
        # Docker
        docker_status = check_docker_status(ep["container"])
        status_icon = "✅" if docker_status == "running" else "❌"
        print(f"   Docker: {status_icon} {docker_status}")
        
        # API
        api_status = check_model_ready(ep["port"])
        if api_status["ready"]:
            print(f"   API:    ✅ Serving: {', '.join(api_status['models'])}")
        else:
            print(f"   API:    ❌ Not responding")
            continue
        
        # Metrics
        metrics = get_vllm_metrics(ep["port"])
        if metrics:
            print(f"   Metrics:")
            for k, v in metrics.items():
                print(f"     • {k}: {v}")
    
    print(f"\n{'='*55}")
    print("✅ Health check complete.")


if __name__ == "__main__":
    main()
