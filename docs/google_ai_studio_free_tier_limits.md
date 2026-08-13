# Bảng Thống Kê Toàn Diện Hạn Mức Free Tier Google AI Studio & Đề Xuất Chiến Lược Cho IDOP / Antigravity

Tài liệu này lưu trữ bảng tra cứu đầy đủ 100% các dòng mô hình, công cụ (Tools), Grounding và Agent hiển thị trên trang **Rate Limit của Google AI Studio Console** (dữ liệu từ project hiện tại).

---

## 1. Bảng Thống Kê Toàn Diện 40 Mô Hình & Agent (Free Tier)

*Ký hiệu:*
- **RPM**: Requests Per Minute (số yêu cầu mỗi phút).
- **TPM**: Tokens Per Minute (số token mỗi phút, K = nghìn, M = triệu).
- **RPD**: Requests Per Day (số yêu cầu mỗi ngày, K = nghìn).
- Dấu **"-"**: Trang không hiển thị chỉ số.
- **Giá trị 0**: Chưa được cấp quota miễn phí trong project hiện tại (cần qua Paid / Proxy).

| STT | Nhóm | Model / Công cụ | RPM | TPM | RPD | Nhận xét nhanh & Ứng dụng |
|---|---|---|---|---|---|---|
| 1 | **Agents** | **Antigravity Agents** | **60** | **100K** | **100** | Quota riêng cho Antigravity Agents/CLI Workflows |
| 2 | Agents | Deep Research Pro Preview | 0 | 0 | 0 | Chưa có quota Free Tier |
| 3 | Text-out models | Gemini 2 Flash | 0 | 0 | 0 | Chưa có quota Free Tier |
| 4 | Text-out models | Gemini 2 Flash Lite | 0 | 0 | 0 | Chưa có quota Free Tier |
| 5 | Other models | Computer Use Preview | 0 | 0 | 0 | Quota bằng 0 trong project hiện tại |
| 6 | Text-out models | Gemini 2.5 Flash | 5 | 250K | 20 | Thử nghiệm text prompt dài |
| 7 | Multi-modal | Nano Banana, Gemini 2.5 Flash Preview Image | 0 | 0 | 0 | Chưa có quota Free Tier |
| 8 | Text-out models | Gemini 2.5 Flash Lite | 10 | 250K | 20 | RPM=10, RPD=20 |
| 9 | Multi-modal | Gemini 2.5 Flash TTS | 3 | 10K | 10 | Quota nhỏ cho TTS |
| 10 | Text-out models | Gemini 2.5 Pro | 0 | 0 | 0 | Pro model chưa có Free Tier |
| 11 | Multi-modal | Gemini 2.5 Pro TTS | 0 | 0 | 0 | Chưa có quota Free Tier |
| 12 | Text-out models | Gemini 3 Flash | 5 | 250K | 20 | Thử nghiệm Flash tiêu chuẩn |
| 13 | Multi-modal | Nano Banana Pro, Gemini 3 Pro Image | 0 | 0 | 0 | Chưa có quota Free Tier |
| 14 | Text-out models | Gemini 3.1 Pro | 0 | 0 | 0 | Chưa có quota Free Tier |
| 15 | Multi-modal | Nano Banana 2, Gemini 3.1 Flash Image | 0 | 0 | 0 | Chưa có quota Free Tier |
| 16 | **Text-out models** | **Gemini 3.1 Flash Lite** | **15** | **250K** | **500** | **Chủ lực RAG/OCR**: RPD cao (500), TPM 250K |
| 17 | Multi-modal | Nano Banana 2 Lite, Gemini 3.1 Flash Lite Image | 0 | 0 | 0 | Chưa có quota Free Tier |
| 18 | Multi-modal | Gemini 3.1 Flash TTS | 3 | 10K | 10 | Quota nhỏ cho TTS |
| 19 | Text-out models | Gemini 3.5 Flash | 5 | 250K | 20 | Thử nghiệm prompt ngữ cảnh dài |
| 20 | **Text-out models** | **Gemini 3.5 Flash Lite** | **15** | **250K** | **500** | **Chủ lực Chatbot/Metadata**: RPD 500 |
| 21 | Text-out models | Gemini 3.6 Flash | 5 | 250K | 20 | Thử nghiệm suy luận mở rộng |
| 22 | **Other models** | **Gemini Embedding 1** | **100** | **30K** | **1K** | Quota cao cho Vector search |
| 23 | **Other models** | **Gemini Embedding 2** | **100** | **30K** | **1K** | **Chủ lực RAG Embedding** cho IDOP |
| 24 | Multi-modal | Gemini Omni Flash | 0 | 0 | 0 | Chưa có quota Free Tier |
| 25 | Other models | Gemini Robotics ER 1.5 Preview | 10 | 250K | 20 | Quota nhóm Robotics Preview |
| 26 | Other models | Gemini Robotics ER 1.6 Preview | 5 | 250K | 20 | Quota nhóm Robotics Preview |
| 27 | Other models | Gemini Robotics ER 2 Preview | 5 | 250K | 20 | Quota nhóm Robotics Preview |
| 28 | **Other models** | **Gemma 4 26B** | **30** | **16K** | **14.4K** | **RPD cực cao (14.4K)** cho request ngắn |
| 29 | **Other models** | **Gemma 4 31B** | **30** | **16K** | **14.4K** | **RPD cực cao (14.4K)** cho request ngắn |
| 30 | Multi-modal | Imagen 4 Fast Generate | - | - | 25 | Sinh ảnh minh họa SOP (25 lượt/ngày) |
| 31 | Multi-modal | Imagen 4 Generate | - | - | 25 | Sinh ảnh tiêu chuẩn (25 lượt/ngày) |
| 32 | Multi-modal | Imagen 4 Ultra Generate | - | - | 25 | Sinh ảnh chất lượng cao (25 lượt/ngày) |
| 33 | Multi-modal | Lyria 3 Clip | 0 | 0 | 0 | Chưa có quota Free Tier |
| 34 | Multi-modal | Lyria 3 Pro | 0 | 0 | 0 | Chưa có quota Free Tier |
| 35 | Multi-modal | Veo 3 Fast Generate | 0 | 0 | 0 | Chưa có quota Free Tier |
| 36 | Multi-modal | Veo 3 Generate | 0 | 0 | 0 | Chưa có quota Free Tier |
| 37 | Multi-modal | Veo 3 Lite Generate | 0 | 0 | 0 | Chưa có quota Free Tier |
| 38 | **Live API** | **Gemini 2.5 Flash Native Audio Dialog** | **Unlimited** | **1M** | **Unlimited** | Live Audio Dialog, TPM 1M |
| 39 | Live API | Gemini 3 Flash Live | Unlimited | 65K | Unlimited | Live API thời gian thực |
| 40 | Live API | Gemini 3.5 Live Translate | Unlimited | 20K | Unlimited | Live Translate phiên dịch tức thì |

---

## 2. Bảng Hạn Mức Công Cụ Tra Cứu (Tool / Grounding Limits)

Các hạn mức dành cho tính năng tra cứu thông tin (Grounding) chủ yếu tính theo **RPD (Requests Per Day)**.

| STT | Nhóm công cụ | Model / Tool | RPM | TPM | RPD | Trạng thái Quota |
|---|---|---|---|---|---|---|
| 1 | Map grounding | Deep Research Pro Preview | - | - | 500 | 500 req/ngày |
| 2 | Map grounding | Gemini 2 Flash | - | - | 500 | 500 req/ngày |
| 3 | Map grounding | Computer Use Preview | - | - | 500 | 500 req/ngày |
| 4 | Map grounding | Gemini 2.5 Flash | - | - | 500 | 500 req/ngày |
| 5 | Map grounding | Gemini 2.5 Flash Lite | - | - | 500 | 500 req/ngày |
| 6 | Map grounding | Gemini 2.5 Pro | - | - | 0 | Không có quota |
| 7 | Map grounding | Gemini 3 Flash | - | - | 0 | Không có quota |
| 8 | Map grounding | Gemini 3.1 Pro | - | - | 0 | Không have quota |
| 9 | Map grounding | Gemini 3.1 Flash Lite | - | - | 500 | 500 req/ngày |
| 10 | Map grounding | Gemini 3.1 Flash TTS | - | - | 500 | 500 req/ngày |
| 11 | Map grounding | Gemini 3.5 Flash | - | - | 0 | Không có quota |
| 12 | Map grounding | Gemini 3.5 Flash Lite | - | - | 500 | 500 req/ngày |
| 13 | Map grounding | Gemini 3.6 Flash | - | - | 0 | Không có quota |
| 14 | Map grounding | Gemini Robotics ER 1.6 Preview | - | - | 500 | 500 req/ngày |
| 15 | Map grounding | Gemini Robotics ER 2 Preview | - | - | 500 | 500 req/ngày |
| 16 | Search grounding | Gemini 2 Search | - | - | 1.5K | **1,500 req/ngày** |
| 17 | Search grounding | Gemini 2.5 Search | - | - | 1.5K | **1,500 req/ngày** |
| 18 | Search grounding | Gemini 3 Search | - | - | 0 | Không có quota |
| 19 | Search grounding | Default Search | - | - | 1.5K | **1,500 req/ngày** |

---

## 3. Chiến Lược Phân Bổ Mô Hình Tối Ưu Cho IDOP / Antigravity

Dựa trên bảng số liệu 100% đầy đủ trên, chiến lược điều hướng (Routing) tối ưu nhất cho nền tảng IDOP / Antigravity được thiết lập như sau:

| Mục tiêu Sử dụng | Lựa chọn Nổi bật | Lý do Chiến lược Quota |
|---|---|---|
| **Antigravity Workflows & CLI** | **Antigravity Agents** | Quota độc lập `60 RPM / 100K TPM / 100 RPD` dành riêng cho agent workflows |
| **Request Nhỏ, Tần suất Cực lớn** | **Gemma 4 26B / Gemma 4 31B** | **14,400 RPD / 30 RPM** (TPM 16K phù hợp cho các prompt/câu lệnh ngắn) |
| **Xử lý Văn bản & Ngữ cảnh Dài** | **Gemini 3.1 Flash Lite / 3.5 Flash Lite** | **500 RPD / 15 RPM / 250K TPM** (Cân bằng hoàn hảo cho OCR & RAG) |
| **Embedding & Vector Search** | **Gemini Embedding 1 / 2** | **1,000 RPD / 100 RPM / 30K TPM** (Nạp tri thức vector hóa) |
| **Search Grounding** | **Default Search / Gemini 2.5 Search** | **1,500 req/ngày** cho tác vụ tra cứu thông tin web thực tế |
| **Sinh ảnh Đồ họa / SOP** | **Imagen 4 Fast / Standard / Ultra** | **25 ảnh/ngày** minh họa quy trình & báo cáo |
| **Live Audio & Hội thoại Thoại** | **Gemini 2.5 Flash Native Audio Dialog** | **Unlimited RPM / RPD** (Cực kỳ mạnh mẽ cho trải nghiệm thoại) |

---
*Tài liệu tra cứu chính thức tại repository `dgx-spark-toolkit` (`docs/google_ai_studio_free_tier_limits.md`).*
