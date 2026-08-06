# Google AI Studio — Free Tier Rate Limits per API Key

> **Nguồn:** Ảnh chụp Dashboard Google AI Studio ngày 31/03/2026.
> **Mục đích:** Tham chiếu khi cấu hình `litellm_config.yaml` để tối ưu hóa AI Gateway.
> **Định dạng:** `Đã dùng / Giới hạn` (per API Key per Model)

---

## 📊 Bảng tổng hợp Rate Limits

### Text-out Models (Gemini)

| Model | RPM | TPM | RPD | Ghi chú |
|---|---|---|---|---|
| **Gemini 3.1 Flash Lite** | 15 | 250K | 500 | ⚡ Model OCR chính (`ocr-primary`, `ocr-fallback`) |
| **Gemini 3 Flash** | 5 | 250K | 20 | ⚠️ RPD rất thấp, chỉ dùng làm fallback nhẹ |
| **Gemini 2.5 Flash** | 5 | 250K | 20 | 🔵 RPD thấp, tiềm năng dùng tier3 |
| **Gemini 2.5 Flash Lite** | 10 | 250K | 20 | 🔵 RPM tốt hơn Flash, RPD thấp |
| Gemini 2.5 Pro | 0 | 0 | 0 | ❌ Không khả dụng Free Tier |
| Gemini 3.1 Pro | 0 | 0 | 0 | ❌ Không khả dụng Free Tier |
| Gemini 2 Flash | 0 | 0 | 0 | ❌ Không khả dụng Free Tier |
| Gemini 2 Flash Lite | 0 | 0 | 0 | ❌ Không khả dụng Free Tier |

### Other Models (Gemma)

| Model | RPM | TPM | RPD | Ghi chú |
|---|---|---|---|---|
| **Gemma 3 27B** | 30 | 15K | 14,400 | 🏆 Model Synthetic Queries chính (`text-gemma`) |
| Gemma 3 12B | 30 | 15K | 14,400 | 🟢 Backup tiềm năng cho text-gemma |
| Gemma 3 4B | 30 | 15K | 14,400 | 🟢 Nhẹ nhất, phù hợp metadata extraction |
| Gemma 3 2B | 30 | 15K | 14,400 | 🟢 Siêu nhẹ |
| Gemma 3 1B | 30 | 15K | 14,400 | 🟢 Nano |

### Multi-modal Generative Models

| Model | RPM | TPM | RPD | Ghi chú |
|---|---|---|---|---|
| Gemini 2.5 Flash TTS | 3 | 10K | 10 | 🔇 Text-to-Speech |
| Imagen 4 Generate | - | - | 25 | 🎨 Image generation |
| Imagen 4 Ultra Generate | - | - | 25 | 🎨 Image generation |
| Imagen 4 Fast Generate | - | - | 25 | 🎨 Image generation |

### Embedding Models

| Model | RPM | TPM | RPD | Ghi chú |
|---|---|---|---|---|
| **Gemini Embedding 1** | 100 | 30K | 1,000 | 📐 Tiềm năng cho hybrid embedding |

---

## 🔑 Tổng năng lực hệ thống (10 API Keys × Free Tier)

### OCR Pipeline (Gemini 3.1 Flash Lite)
- **Tổng RPM:** 10 × 15 = **150 requests/phút**
- **Tổng RPD:** 10 × 500 = **5,000 trang/ngày**
- **Tổng TPM:** 10 × 250K = **2.5M tokens/phút**

### Synthetic Queries (Gemma 3 27B)
- **Tổng RPM:** 10 × 30 = **300 requests/phút**
- **Tổng RPD:** 10 × 14,400 = **144,000 queries/ngày**
- **Tổng TPM:** 10 × 15K = **150K tokens/phút**

### OCR Fallback Tiers (Gemini 2.5 Flash)
- **Tổng RPM:** 10 × 5 = **50 requests/phút**
- **Tổng RPD:** 10 × 20 = **200 trang/ngày** (chỉ dùng khi Flash Lite cạn)

---

## ⚡ Trạng thái sử dụng thực tế (Snapshot 31/03/2026)

| Model | RPM (Used/Limit) | RPD (Used/Limit) | Tình trạng |
|---|---|---|---|
| Gemini 3.1 Flash Lite | 30/15 | 532/500 | 🔴 **VƯỢT NGƯỠNG** — Cần giảm tải OCR |
| Gemini 3 Flash | 5/5 | 56/20 | 🔴 **VƯỢT NGƯỠNG** — RPD đã cạn |
| Gemma 3 27B | 29/30 | 702/14,400 | 🟡 RPM gần ngưỡng, RPD còn dư rất nhiều |
| Gemini 2.5 Flash | 3/5 | 15/20 | 🟢 Còn dư |
| Gemini 2.5 Flash Lite | 3/10 | 14/20 | 🟢 Còn dư |

---

## 🧭 Chiến lược Vận hành AI Gateway

### 1. Nguyên tắc Lệch pha (Phase-Shifted Key Routing)
- Tất cả 10 Keys đều đăng ký cho cả OCR lẫn Gemma.
- LiteLLM `usage-based-routing` tự động chọn Key có Counter thấp nhất trên Redis.
- Pipeline xử lý tuần tự (S03→S06) nên OCR và Gemma tự nhiên lệch pha theo thời gian.

### 2. Ưu tiên Model theo chi phí Quota
1. **OCR chính:** Gemini 3.1 Flash Lite (RPD cao nhất = 500/key)
2. **OCR dự phòng:** Gemini 2.5 Flash / 2.5 Flash Lite (RPD=20, chỉ dùng khi Flash Lite cạn)
3. **Synthetic Queries:** Gemma 3 27B (RPD=14,400 — gần như vô hạn)
4. **Local GPU (rag-core):** Chốt chặn cuối cùng, không tốn API Quota

### 3. Cảnh báo vận hành
- **Flash Lite RPD=500/key/ngày:** Với 10 Keys = 5,000 trang OCR/ngày. Nếu cần xử lý nhiều hơn, phải dùng Local GPU (rag-core) bổ sung.
- **Gemma TPM=15K/key:** Thấp hơn Gemini (250K). Cần giữ prompt ngắn gọn (<512 tokens) cho synthetic queries.
- **Gemini 3 Flash RPD=20:** Quá thấp để dùng làm OCR chính. Chỉ nên đặt ở ocr-tier3/tier4.

### 4. Models chưa khai thác (Cơ hội)
- **Gemma 3 4B/12B:** Cùng RPM/RPD với 27B. Có thể đăng ký thêm để mở rộng pool text-gemma.
- **Gemini Embedding 1:** RPM=100, RPD=1000. Tiềm năng cho hybrid search embedding.
