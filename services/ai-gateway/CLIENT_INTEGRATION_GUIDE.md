# AI Gateway Client Integration Guide

Tài liệu này quy định hợp đồng giao tiếp chuẩn (Client Integration Contract) giữa các ứng dụng Client (`ccba-ai`, RAG Service, Open-WebUI, BIM Planner, script tự động...) và **AI Gateway trên Server Spark**.

---

## 📡 Thông số Kết nối (Connection Specs)

- **Local Endpoint**: `http://localhost:8090/v1`
- **Tailscale VPN Endpoint**: `http://100.83.192.30:8090/v1`
- **Authentication**: `Bearer sk-spark-secure-key-2026`
- **Format**: Chuẩn OpenAI REST API (`/chat/completions`, `/embeddings`, `/models`)

---

## 🏛️ 4 Model Archetypes (Vai trò Nghiệp vụ Chuẩn)

Khi tích hợp từ phía client, hãy chọn model theo đúng Archetype nghiệp vụ:

| Archetype | Model Aliases | Target Backend | Khi nào sử dụng? |
| :--- | :--- | :--- | :--- |
| **1. OCR & Vision Ingestion** | `ocr-primary`<br>`ocr-fallback`<br>`ocr-tier4` | Google AI Studio Direct (10 keys) | Xử lý OCR tài liệu PDF, bản vẽ, hình ảnh, văn bản pháp luật. |
| **2. Standard General / Coding** | `gemini-3.8-flash`<br>`gemini-3.7-flash`<br>`gemini-3.7-flash-medium`<br>`text-gemma` | Google API + Centralized Proxy | Chat tổng quát, code sinh tự động, tóm tắt bài viết, đàm thoại agent. |
| **3. Deep Reasoning / Complex Audit** | `gemini-3.8-flash-high`<br>`gemini-3.7-flash-high`<br>`claude-sonnet-4-6-thinking`<br>`reasoning-gemma` | Google API + Centralized Proxy | Phân tích điều khoản hợp đồng phức tạp, đối soát pháp lý, suy luận đa bước. |
| **4. Local Private / Zero-Cost** | `rag-core`<br>`qwen-local-primary` | vLLM Qwen 35B Local (GPU DGX) | Chạy offline, dữ liệu tuyệt mật nội bộ, fallback chốt chặn khi mất Internet. |

---

## ⚙️ Quy tắc Hợp đồng Tích hợp (Client Contract Rules)

### 1. Quy tắc HTTP Timeout (Bắt buộc: 30s – 60s)
- **Lý do**: AI Gateway triển khai cơ chế **Fallback Cascade** đa tầng (tự động thử 10 keys và chuyển tầng khi upstream gặp lỗi 503/429). 
- **Quy tắc**: Phía client **PHẢI** cấu hình `timeout >= 30s` (khuyến nghị `45s - 60s`). Không cấu hình timeout quá ngắn (<15s) để tránh ngắt kết nối khi Gateway đang failover mượt mà sang model dự phòng.

### 2. Zero-Config Thinking Parameters
- Phía client **KHÔNG CẦN** tự tạo cấu trúc Google-specific như `generationConfig.thinking_config` hay `thinking_budget`.
- AI Gateway tích hợp sẵn bộ tiền xử lý `custom_callbacks.gemini_corrector` tự động chuẩn hóa, chèn và lọc tham số suy luận theo từng model (`-low`, `-medium`, `-high`).

---

## 💻 Code Mẫu Tích hợp Chuẩn (Production Ready)

### 1. Python SDK `ccba-ai` (Khuyến nghị cho Hub/Spoke)
```python
from ccba_ai import ai

# Chat cơ bản
response = ai.chat(
    "Tóm tắt các điểm chính trong tài liệu đính kèm...",
    model="gemini-3.7-flash"
)
print(response)

# Deep reasoning với Gemini 3.7 High
deep_res = ai.chat(
    "Phân tích xung đột giữa Điều 12 và Điều 18 của dự thảo...",
    model="gemini-3.7-flash-high"
)
print(deep_res)
```

### 2. Python `openai` SDK
```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.getenv("AI_GATEWAY_URL", "http://100.83.192.30:8090/v1"),
    api_key=os.getenv("AI_GATEWAY_KEY", "sk-spark-secure-key-2026"),
    timeout=60.0  # Khuyến nghị 30s - 60s
)

completion = client.chat.completions.create(
    model="gemini-3.7-flash",
    messages=[
        {"role": "system", "content": "Bạn là trợ lý AI chuyên nghiệp."},
        {"role": "user", "content": "Viết script Python trích xuất bảng từ PDF."}
    ],
    temperature=0.3
)

print(completion.choices[0].message.content)
```

### 3. TypeScript / JavaScript (`fetch` trên Web/Node.js)
```typescript
interface ChatResponse {
  choices: Array<{
    message: {
      content: string;
      role: string;
    };
  }>;
}

async function callAiGateway(prompt: string, model: string = "gemini-3.7-flash"): Promise<string> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 45000); // 45s timeout

  try {
    const response = await fetch("http://100.83.192.30:8090/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-spark-secure-key-2026"
      },
      body: JSON.stringify({
        model: model,
        messages: [{ role: "user", content: prompt }]
      }),
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`AI Gateway error: HTTP ${response.status} - ${await response.text()}`);
    }

    const data: ChatResponse = await response.json();
    return data.choices[0]?.message?.content || "";
  } finally {
    clearTimeout(timeoutId);
  }
}
```

### 4. Bash `curl` (Kiểm tra nhanh)
```bash
curl -s -X POST "http://localhost:8090/v1/chat/completions" \
  -H "Authorization: Bearer sk-spark-secure-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.7-flash",
    "messages": [{"role": "user", "content": "Hello, health check!"}]
  }' | jq .choices[0].message.content
```

---

## 🛡️ Sơ đồ Chuyển vùng Dự phòng (Fallback Cascade)

```mermaid
graph TD
    User([Client Request]) --> ModelChoice{Model Requested}
    
    ModelChoice -->|gemini-3.7-flash-high| G37H[gemini-3.7-flash-high]
    G37H -->|503/429/Timeout| G37M[gemini-3.7-flash-medium]
    G37M -->|503/429/Timeout| G36H[gemini-3.6-flash-high]
    G36H -->|503/429/Timeout| G35H[gemini-3.5-flash-high]
    G35H -->|503/429/Timeout| OCT4[ocr-tier4: gemini-2.5-flash]
    OCT4 -->|503/429/Timeout| RAGC[rag-core: Local Qwen 35B GPU]
    
    ModelChoice -->|ocr-primary| OCR1[ocr-primary: gemini-3.1-flash-lite]
    OCR1 -->|503/429/Timeout| OCRFB[ocr-fallback: gemini-3.5-flash-lite]
    OCRFB -->|503/429/Timeout| OCT4
```
