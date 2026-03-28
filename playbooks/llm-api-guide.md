# LLM API Integration Guide

## AI Gateway (Recommended — 22 Models)

All AI access should go through the **AI Gateway** for unified routing, fallbacks, and cloud model support.

### Gateway Endpoint

```
http://localhost:8090/v1          (local)
http://100.83.192.30:8090/v1     (remote via Tailscale)
Authorization: Bearer $LITELLM_MASTER_KEY
```

### Quick Test

```bash
curl http://localhost:8090/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## Available Models

### 🖥️ Local GPU — Private / Offline
| Model | Description |
|-------|-------------|
| `qwen3.5-35b` | Qwen 3.5 35B — main local model |
| `rag-core` | Alias of qwen3.5-35b (RAG pipeline) |
| `rag-light` | Qwen 3.5 4B — lightweight fallback |

### 🏎️ Speed Tier (< 1.5s)
| Model | Best For |
|-------|----------|
| `gemini-3-flash` | Fast multimodal + reasoning |
| `gemini-3.1-flash-lite` | Cheapest & fastest Gemini |
| `gemma-3-27b` | Free tier, high-volume tasks |
| `claude-haiku-4` | Fast Claude |
| `claude-haiku-4-5` | Faster Claude, better quality |

### 🧠 Balanced Tier (1–3s)
| Model | Best For |
|-------|----------|
| `claude-sonnet-4-6` ⭐ | Coding, agentic pipelines |
| `claude-sonnet-4-5` | Previous gen Sonnet |
| `claude-sonnet-4-6-thinking` | Reasoning with CoT |
| `claude-sonnet-4-5-thinking` | Reasoning (previous gen) |
| `claude-opus-4-6` | Deep analysis, legal/financial |
| `claude-opus-4-5` | Previous gen Opus |
| `claude-opus-4-6-thinking` | Opus + chain-of-thought |
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

## Python Integration

```python
from openai import OpenAI

# Via Gateway (recommended — all models + fallbacks)
client = OpenAI(
    base_url="http://localhost:8090/v1",
    api_key=os.environ["LITELLM_MASTER_KEY"]
)

response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=1024
)
print(response.choices[0].message.content)
```

---

## Direct vLLM (Local Models Only)

Use only when you need raw vLLM access without gateway routing:

```bash
# Qwen 3.5 35B (port 8004)
curl http://localhost:8004/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3.5-35b", "messages": [{"role": "user", "content": "Hello!"}]}'
```

> ⚠️ Direct vLLM access has no fallbacks and no cloud models. Prefer the gateway.

---

## Remote Access (Máy Khác)

Để sử dụng Gateway từ máy khác, xem:
- **Hướng dẫn chi tiết**: [`client-setup-guide.md`](./client-setup-guide.md)
- **Files cấu hình sẵn**: [`examples/client-setup/`](../examples/client-setup/)
- **Test kết nối**: `bash examples/client-setup/test-connection.sh`
