# NVIDIA DGX Spark Toolkit

Comprehensive AI development toolkit for NVIDIA DGX Spark. Provides a unified **AI Gateway** routing to local vLLM models (Qwen 3.5) and a remote proxy (Claude 4.x, Gemini 3.x, GPT-4).

## Hardware

| | |
|---|---|
| **Chip** | GB10 Grace Blackwell Superchip |
| **Memory** | 128GB LPDDR5x unified |
| **Performance** | 1 petaFLOP (FP4) |
| **OS** | DGX OS (Ubuntu 24.04) |
| **Tailscale IP** | `100.83.192.30` |
| **LAN IP** | `192.168.1.27` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Gateway :8090                        │
│                  (LiteLLM Proxy — 25 models)                │
└──────┬──────────────────┬────────────────┬──────────────────┘
       │                  │                │
   Local vLLM         Remote Proxy     Cloud Direct
   :8004 (35B)     100.79.241.120      Gemini / Groq
   qwen3.5-35b      claude/gemini/gpt   (fallback)
        │
   RAG Service :8005
   (Milvus + Reranker)
        │
   Hybrid Ingestion
   (PaddleOCR + Qwen3.5 Vision)
```

```
dgx-spark-toolkit/
├── .agents/skills/          # AI Agent Skills (11 skills)
│   └── shared/vllm_client.py  # Unified gateway client
├── services/
│   ├── ai-gateway/             # LiteLLM config (25 models)
│   └── rag-service/            # RAG pipeline (FastAPI + BGE-M3)
├── monitoring/                 # Prometheus + Grafana
├── playbooks/                  # Setup guides
├── scripts/                    # start-all, stop-all, setup-remote
└── docker-compose.yml
```

---

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env — set GATEWAY_PROXY_KEY from your proxy admin
```

### 2. Start Everything

```bash
bash scripts/start-all.sh
```

This starts vLLM (Qwen 3.5 35B) + Docker stack (Gateway + RAG + Milvus + Monitoring).

### 3. Test the Gateway

```bash
# List all 25 available models
curl http://localhost:8090/v1/models \
  -H "Authorization: Bearer sk-spark-secure-key-2026"

# Run inference
curl http://localhost:8090/v1/chat/completions \
  -H "Authorization: Bearer sk-spark-secure-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## Available Models (via AI Gateway)

### 🏎️ Tier 1 — Speed (< 1.5s)
| Model | Best For |
|-------|----------|
| `gemini-2.5-flash` | Real-time chat, autocomplete |
| `gemini-2.5-flash-lite` | High-volume batch tasks |
| `gemini-3-flash` | Fast multimodal + reasoning |
| `gpt-4o` | Vision + general purpose |
| `gpt-4o-mini` | Cost-efficient GPT-4 class |
| `claude-3-haiku` | Fast Claude, customer agents |
| `qwen3.5-35b` | **Local** — private data, offline |

### 🧠 Tier 2 — Balanced (1–3s)
| Model | Best For |
|-------|----------|
| `claude-sonnet-4-6` ⭐ | **Default** — coding, agents (SWE-bench 79.6%) |
| `claude-sonnet-thinking` | Code review with chain-of-thought |
| `claude-opus-4-5` | Deep analysis, financial/legal |
| `gpt-4-turbo` | Complex coding, JSON generation |
| `gemini-2.5-flash-thinking` | Reasoning with thinking |

### 🔬 Tier 3 — Deep Reasoning (7–13s, 1M context)
| Model | Best For |
|-------|----------|
| `gemini-3.1-pro` | Full codebase analysis, research |
| `gemini-3-pro-high` | Scientific reasoning (GPQA 94.3%) |
| `gemini-3.1-pro-high` | ARC-AGI-2 tasks, novel problems |

---

## Remote Access

```bash
# Open firewall (one-time setup)
sudo bash scripts/setup-remote-access.sh

# Connect from any machine
curl http://100.83.192.30:8090/v1/models \
  -H "Authorization: Bearer sk-spark-secure-key-2026"
```

**Python:**
```python
from openai import OpenAI
client = OpenAI(base_url="http://100.83.192.30:8090/v1", api_key="sk-spark-secure-key-2026")
```

See [`playbooks/remote-access.md`](playbooks/remote-access.md) for full details.

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| AI Gateway | `8090` | LiteLLM proxy — 25 models |
| RAG Service | `8005` | BIM semantic search + generation |
| RAG Preview | `/preview/{fn}/{pg}` | GET page images for citations |
| Qwen 3.5 35B | `8004` | Local vLLM (NVFP4, ~20GB) |
| Milvus | `19530` | Vector database |
| Prometheus | `9090` | Metrics |
| Grafana | `3000` | Dashboards |

---

## AI Skills

All skills in `.agent/skills/` use the shared gateway client (`shared/vllm_client.py`) and automatically get access to all models + cloud fallbacks.

| Skill | Description |
|-------|-------------|
| `ai-ui-builder` | Mockup → React/Tailwind code (Qwen3-VL) |
| `visual-qa-automator` | Visual regression testing |
| `multimodal-ocr` | Document OCR & data extraction |
| `bim-dev-ops` | BIM development operations |
| `bim-qa-pipeline` | BIM quality assurance |
| `idop-app-scaffolder` | IDOP module scaffolding |
| `idop-crud-generator` | IDOP CRUD generation |
| `m365-integrator` | Microsoft 365 Graph API integration |
| `infrastructure-manager` | Server & service management |
| `vllm-manager` | vLLM model serving & monitoring |

---

## Links

- [NVIDIA DGX Spark Docs](https://docs.nvidia.com/dgx-spark/)
- [vLLM Documentation](https://docs.vllm.ai/)
- [LiteLLM Docs](https://docs.litellm.ai/)
