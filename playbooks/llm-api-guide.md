# LLM API Integration Guide

## AI Gateway (Recommended — 25 Models)

All AI access should go through the **AI Gateway** for unified routing, fallbacks, and cloud model support.

### Gateway Endpoint

```
http://localhost:8090/v1          (local)
http://100.83.192.30:8090/v1     (remote via Tailscale)
Authorization: Bearer sk-spark-secure-key-2026
```

### Quick Test

```bash
curl http://localhost:8090/v1/chat/completions \
  -H "Authorization: Bearer sk-spark-secure-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## Available Models

### 🏎️ Speed Tier (< 1.5s)
| Model | Best For |
|-------|----------|
| `gemini-2.5-flash` | Real-time chat, autocomplete |
| `gemini-3-flash` | Fast multimodal reasoning |
| `gpt-4o` | Vision + general purpose |
| `gpt-4o-mini` | Cost-efficient |
| `claude-3-haiku` | Fast Claude |
| `qwen3.5-35b` | **Local** — private/offline |

### 🧠 Balanced Tier (1–3s)
| Model | Best For |
|-------|----------|
| `claude-sonnet-4-6` ⭐ | Coding, agentic pipelines |
| `claude-sonnet-thinking` | Reasoning with CoT |
| `claude-opus-4-5` | Legal, financial analysis |
| `gpt-4-turbo` | Complex coding |

### 🔬 Deep Reasoning (7–13s, 1M context)
| Model | Best For |
|-------|----------|
| `gemini-3.1-pro` | Full codebase analysis |
| `gemini-3-pro-high` | Scientific reasoning |
| `gemini-3-pro` | Multi-source research |

### ☁️ Fallbacks
| Model | Backend |
|-------|---------|
| `gemini-direct` | Google Gemini API |
| `groq-llama3` | Groq LPU API |

---

## Python Integration

```python
from openai import OpenAI

# Via Gateway (recommended — all models + fallbacks)
client = OpenAI(
    base_url="http://localhost:8090/v1",
    api_key="sk-spark-secure-key-2026"
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
curl http://100.83.192.30:8004/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3.5-35b", "messages": [{"role": "user", "content": "Hello!"}]}'
```

> ⚠️ Direct vLLM access has no fallbacks and no cloud models. Prefer the gateway.
