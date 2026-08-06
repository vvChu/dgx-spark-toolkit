# NVIDIA DGX Spark Toolkit

Comprehensive AI development toolkit for NVIDIA DGX Spark. Provides a unified **AI Gateway** routing to local vLLM models (Qwen 3.5) and cloud proxies (Claude 4.x, Gemini 3.x, GPT-OSS).

## Hardware

| | |
|---|---|
| **Chip** | GB10 Grace Blackwell Superchip |
| **Memory** | 128GB LPDDR5x unified |
| **Performance** | 1 petaFLOP (FP4) |
| **OS** | DGX OS (Ubuntu 24.04) |
| **Hostname** | `spark-CCBA` |
| **Tailscale IP** | `100.83.192.30` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Gateway :8090                        │
│              (LiteLLM Proxy — 22 models)                    │
└──────┬──────────────────┬────────────────┬──────────────────┘
       │                  │                │
   Local vLLM         Gateway Proxy    Cloud Direct
   :8004 (35B)        Claude/Gemini    Gemini (6 keys)
   :8003 (4B)         GPT-OSS         Gemma-3-27B
   qwen3.5-35b                        (load-balanced)
        │
   RAG Service :8005
   (Milvus + Neo4j + BGE-M3)
        │
   Hybrid Ingestion
   (Surya OCR + Gemini Vision)
```

```
dgx-spark-toolkit/
├── .agents/
│   ├── skills/              # AI Agent Skills (18 skills)
│   │   └── shared/vllm_client.py  # Unified gateway client
│   └── workflows/           # Slash-command workflows (14)
├── services/
│   ├── ai-gateway/          # LiteLLM config (22 models, 38 routes)
│   ├── rag-service/         # RAG pipeline (FastAPI + BGE-M3)
│   └── frontend/            # React 19 + Vite 7 + Tailwind 4
├── monitoring/              # Prometheus + Grafana
├── playbooks/               # Setup guides & API docs
├── examples/                # Client integration examples
├── scripts/                 # start-all, stop-all, setup-remote
└── docker-compose.yml
```

---

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env — set API keys and passwords
```

### 2. Start Everything

```bash
bash scripts/start-all.sh
```

This starts vLLM (Qwen 3.5 35B) + Docker stack (Gateway + RAG + Milvus + Neo4j + Monitoring).

### 3. Test the Gateway

```bash
# List all 22 available models
curl http://localhost:8090/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"

# Run inference
curl http://localhost:8090/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## Available Models (via AI Gateway)

### 🖥️ Local GPU — Private / Offline / High Throughput
| Model | Description |
|-------|-------------|
| `qwen3.5-35b` | Qwen 3.5 35B — main local model (32K context) |
| `rag-core` | Alias of qwen3.5-35b (used by RAG pipeline) |
| `rag-light` | Qwen 3.5 4B — lightweight fallback |

### 🏎️ Speed Tier (< 1.5s)
| Model | Best For |
|-------|----------|
| `gemini-3-flash` | Fast multimodal + reasoning (6-key load-balanced) |
| `gemini-3.1-flash-lite` | Cheapest & fastest Gemini (6-key load-balanced) |
| `gemma-3-27b` | Free tier, high-volume metadata (6-key load-balanced) |
| `claude-haiku-4` | Fast Claude |
| `claude-haiku-4-5` | Faster Claude with better quality |

### 🧠 Balanced Tier (1–3s)
| Model | Best For |
|-------|----------|
| `claude-sonnet-4-6` ⭐ | **Default** — coding, agentic pipelines |
| `claude-sonnet-4-5` | Previous gen Sonnet |
| `claude-sonnet-4-6-thinking` | Reasoning with chain-of-thought |
| `claude-sonnet-4-5-thinking` | Reasoning (previous gen) |
| `claude-opus-4-6` | Deep analysis, legal/financial |
| `claude-opus-4-5` | Previous gen Opus |
| `claude-opus-4-6-thinking` | Opus + CoT |
| `claude-opus-4-5-thinking` | Previous gen Opus + CoT |
| `gpt-oss-120b-medium` | Large OSS model via proxy |

### 🔬 Deep Reasoning (7–13s, 1M context)
| Model | Best For |
|-------|----------|
| `gemini-3.1-pro` | Full codebase analysis, research |
| `gemini-3.1-pro-high` | ARC-AGI-2, novel problems |
| `gemini-3.1-pro-low` | Cost-efficient Gemini Pro |
| `gemini-3-pro-high` | Scientific reasoning |
| `gemini-3-pro-low` | Budget deep reasoning |

---

## Remote Access

```bash
# Open firewall (one-time setup on server)
sudo bash scripts/setup-remote-access.sh

# Connect from any machine via Tailscale
curl http://100.83.192.30:8090/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

**Python:**
```python
from openai import OpenAI
client = OpenAI(base_url="http://100.83.192.30:8090/v1", api_key=os.environ["LITELLM_MASTER_KEY"])
```

See [`playbooks/client-setup-guide.md`](playbooks/client-setup-guide.md) for full setup guide with config files.

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| AI Gateway | `8090` | LiteLLM proxy — 22 models, auto-fallback |
| RAG Service | `8005` | Vietnamese legal document search + generation |
| RAG Frontend | `5173` | React 19 web UI |
| Qwen 3.5 35B | `8004` | Local vLLM (FP8 KV, ~85% GPU) |
| Qwen 3.5 4B | `8003` | Local vLLM fallback (on-demand) |
| Milvus | `19530` | Vector database (BGE-M3 dense+sparse) |
| Neo4j | `7474`/`7687` | Knowledge graph |
| Prometheus | `9090` | Metrics collection |
| Grafana | `3000` | Dashboards |

---

## AI Skills

All 18 skills in `.agents/skills/` use the shared gateway client (`shared/vllm_client.py`) and automatically get access to all models + cloud fallbacks.

| Skill | Description |
|-------|-------------|
| `ai-ui-builder` | Mockup → React/Tailwind code (Qwen 3.5 Vision) |
| `audit` | Linters, tests, security checks on RAG service |
| `autoresearch-runner` | Karpathy-style RAG optimization loop |
| `bim-dev-ops` | BIM Planner development operations |
| `bim-qa-pipeline` | BIM quality assurance testing |
| `fix-frontmatter` | Validate/fix YAML frontmatter in skills |
| `idop-app-scaffolder` | IDOP module scaffolding |
| `idop-crud-generator` | IDOP CRUD code generation |
| `infrastructure-manager` | Server & service management |
| `legal-doc-processor` | Vietnamese legal document processing |
| `m365-integrator` | Microsoft 365 Graph API integration |
| `md-quality-auditor` | Markdown quality assessment vs PDF source |
| `multimodal-ocr` | Invoice/drawing OCR → JSON |
| `python-production-guidelines` | Python/FastAPI/RAG architecture guidelines |
| `rag-audit-runner` | RAG quality audit → structured JSON scorecard |
| `rag-local-python-runner` | Pipeline + audit + evaluate runner |
| `visual-qa-automator` | Visual regression testing (CSS/Layout) |
| `vllm-manager` | vLLM model serving & monitoring |

---

## Links

- [NVIDIA DGX Spark Docs](https://docs.nvidia.com/dgx-spark/)
- [vLLM Documentation](https://docs.vllm.ai/)
- [LiteLLM Docs](https://docs.litellm.ai/)
