# Google AI Studio — Free Tier Rate Limits per API Key

> **Nguồn:** Cập nhật Live Model Discovery ngày 14/08/2026.  
> **Mục đích:** Tham chiếu khi cấu hình `litellm_config.yaml` để tối ưu hóa AI Gateway.  
> **Định dạng:** `Đã dùng / Giới hạn` (per API Key per Model)

---

## 📊 Bảng tổng hợp Rate Limits

### Text & Vision Models (Gemini)

| Model | RPM | TPM | RPD | Ghi chú |
|---|---|---|---|---|
| **Gemini 3.7 Flash** | 5 | 250K | 100 | 🚀 Model mới nhất (`gemini-3.7-flash`, low/med/high) |
| **Gemini 3.6 Flash** | 5 | 250K | 100 | ⚡ Model thế hệ 3.6 (`gemini-3.6-flash-high/med/low`) |
| **Gemini 3.5 Flash** | 5 | 250K | 20 | 🔵 Tier trung gian dự phòng |
| **Gemini 3.1 Flash Lite** | 15 | 250K | 500 | ⚡ Model OCR chính (`ocr-primary`, `ocr-fallback`) |
| **Gemini 2.5 Flash** | 5 | 250K | 20 | 🔵 RPD thấp, chốt chặn tier 4 (`ocr-tier4`) |
| **Gemini 2.5 Flash Lite** | 10 | 250K | 20 | 🔵 RPM tốt hơn Flash, RPD thấp |
| Gemini 2.5 Pro / 3.1 Pro | 0 | 0 | 0 | ❌ Cần cấp phép / Proxy (`100.83.192.30:8045`) |

### Open Reasoning Models (Gemma)

| Model | RPM | TPM | RPD | Ghi chú |
|---|---|---|---|---|
| **Gemma 4 31B IT** | 15 | 250K | 1,500 | 🏆 Model Reasoning chính (`reasoning-gemma`, `text-gemma`) |
| **Gemma 4 26B A4B IT** | 15 | 250K | 1,500 | 🟢 Model MoE Reasoning dự phòng (`reasoning-fallback`) |
| Gemma 3 27B / 12B / 4B | 30 | 15K | 14,400 | 🟢 Dòng Gemma 3 trước đó |

### Multi-modal & Media Models

| Model | RPM | TPM | RPD | Ghi chú |
|---|---|---|---|---|
| Imagen 4 Generate | - | - | 25 | 🎨 Image generation |
| Imagen 4 Ultra / Fast | - | - | 25 | 🎨 Image generation chuyên sâu |
| Veo 3.1 Generate | - | - | 10 | 🎬 Video generation preview |

### Embedding Models

| Model | RPM | TPM | RPD | Ghi chú |
|---|---|---|---|---|
| **Gemini Embedding 2** | 100 | 30K | 1,000 | 📐 Hybrid Embedding đa ngôn ngữ (`gemini-embed`) |

---

## 🔑 Tổng năng lực hệ thống (10 API Keys × Free Tier)

### 1. General & Reasoning Pipeline (Gemini 3.7 Flash)
- **Tổng RPM:** 10 × 5 = **50 requests/phút**
- **Tổng RPD:** 10 × 100 = **1,000 requests/ngày**
- **Tổng TPM:** 10 × 250K = **2.5M tokens/phút**

### 2. OCR Ingestion Pipeline (Gemini 3.1 Flash Lite)
- **Tổng RPM:** 10 × 15 = **150 requests/phút**
- **Tổng RPD:** 10 × 500 = **5,000 trang/ngày**
- **Tổng TPM:** 10 × 250K = **2.5M tokens/phút**

### 3. Open Reasoning Pipeline (Gemma 4 31B)
- **Tổng RPM:** 10 × 15 = **150 requests/phút**
- **Tổng RPD:** 10 × 1,500 = **15,000 queries/ngày**
- **Tổng TPM:** 10 × 250K = **2.5M tokens/phút**

### 4. Embedding Pipeline (Gemini Embedding 2)
- **Tổng RPM:** 10 × 100 = **1,000 requests/phút**
- **Tổng RPD:** 10 × 1,000 = **10,000 embeddings/ngày**

---

## 🧭 Chiến lược Điều phối & Fallback Cascade

```
[Client Request]
       │
       ▼
[Gemini 3.7 Flash High] ────(503 / 429)────► [Gemini 3.7 Flash Medium]
                                                       │
                                                       ▼
[Gemini 3.5 Flash High] ◄────(503 / 429)──── [Gemini 3.6 Flash High]
       │
       ▼
[ocr-tier4 (Gemini 2.5)] ────(503 / 429)───► [rag-core (Local GPU Qwen 35B)]
```

### Quy tắc Vận hành:
1. **Upstream Timeout 25s**: Thiết lập thời gian chờ tối đa 25s cho mỗi deployment Google API để phát hiện nhanh lỗi 503 và kích hoạt ngay fallback cascade.
2. **Client Timeout Khuyến nghị**: Client thiết lập `timeout: 30s - 60s` để đảm bảo chuỗi fallback hoàn tất thông suốt.
3. **Chốt chặn cuối cùng (Local GPU)**: `rag-core` chạy trực tiếp trên GPU DGX Spark không phụ thuộc vào Internet hay API quota ngoài.
