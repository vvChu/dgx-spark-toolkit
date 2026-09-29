# Nghiên Cứu Kiến Trúc: Mô Hình "System One" Jev (TypeSafe AI) & Bài Toán Phân Tách Quyết Định Trong GTM AI Của John Kutay (Rippling)

> **Tác giả nghiên cứu:** Antigravity (Pair Architect) & Grok 4.7 (Auditor & Peer Reviewer)  
> **Thời điểm:** 2026-09-28 23:28 ICT  
> **Nguồn sơ cấp:**  
> - John Kutay (Rippling): *"How Jev Wins (and loses)"* ([X Post / Article 2104276026838925424](https://x.com/JohnKutay/status/2104276026838925424))  
> - Diogo Almeida (TypeSafe AI): *System One Decision Architecture*  
> - Vivek Trivedy (@Vtrivedy10): *Jev for RAG & Small vs Large Corpus Scoring* ([X Post 2102808794493321714](https://x.com/Vtrivedy10/status/2102808794493321714))  
> - Cơ sở lý thuyết: ColBERT (*Contextualized Late Interaction*, Khattab & Zaharia 2020), BGE-M3 (*Multi-Functionality Embedding*, Chen et al. 2024), DeBERTa (*Disentangled Attention*, He et al. 2021).  
> **Mã nguồn đối chiếu:** `services/rag-service/retrieval/search_pipeline.py`, `retrieval/reranker.py`, `services/ai-gateway/litellm_config.yaml`.

---

## 1. Tóm Tắt Điều Hành (Executive Summary)

Ngày 27/09/2026, John Kutay (Trưởng nhóm GTM/Growth AI Engineering tại Rippling) công bố bài nghiên cứu thực nghiệm *"How Jev Wins (and loses)"*, ghi nhận kết quả ứng dụng mô hình **Jev** của **TypeSafe AI** (sáng lập bởi cựu nghiên cứu viên OpenAI Diogo Almeida) bên trong nền tảng **GrowthOS**.

Nghiên cứu làm sáng tỏ một bước chuyển biến quan trọng của kỹ nghệ AI năm 2026: **Sự phân tách giữa Mô hình Hỗ trợ (Assistance — System Two) và Mô hình Quyết định (Decision-Making — System One)**.
- **LLM truyền thống** hoạt động cực kỳ xuất sắc khi có con người trong vòng lặp (HITL), nhưng thường **không đủ ổn định và quá chậm chạp/tốn kém** khi được giao nhiệm vụ đưa ra quyết định tự động, lặp đi lặp lại ở quy mô lớn.
- **Jev (System One)** đạt **90% độ chính xác** (so với **50%** của LLM baseline) và chạy **nhanh hơn gần 8 lần** trong bài toán phân loại chất lượng thông điệp tiếp cận (outreach scoring). Tuy nhiên, Jev **thất bại hoàn toàn** trong bài toán Text-to-SQL vì thiếu khả năng suy luận ngữ cảnh kinh doanh đa bước.
- **Hệ quả cho DGX Spark & CCBA Platform**: Hệ thống của chúng ta đang mắc lỗi kiến trúc khi dùng LLM sinh từ (`claude-haiku-4` / `rag-core` Qwen 35B FP8 trong `stage1_fast_batch_rerank`) để lọc JSON indices — tức **đang đốt tài nguyên System Two vào một bài toán thuần túy System One**. Cần cấu trúc lại để bàn giao toàn bộ các tác vụ phân loại/chấm điểm đóng cho các encoder/scorer chuyên dụng (`bge-reranker-v2-m3`).

---

## 2. Giải Phẫu Kiến Trúc: "System One" AI & Mô Hình Jev

### 2.1. Phân Định Bản Chất: Generative LLM vs System One Model

| Tiêu chí kỹ thuật | Autoregressive LLM (System Two) | System One Model (Jev / Fast Scorer) |
|---|---|---|
| **Cơ chế hoạt động** | Sinh từ tự hồi quy tuần tự (Token-by-token decoding) | Lấy mẫu song song trực tiếp (Parallel Sampler / Direct Head) |
| **Không gian đầu ra** | Chuỗi văn bản tự do không biên giới (Open-ended prose, JSON code blocks) | Quyết định có kiểu định nghĩa trước (Typed Decision: Choice, Score, Noul) |
| **Độ trễ trung bình** | $400\text{ms} - 5000\text{ms}$ (phụ thuộc độ dài token sinh ra) | $5\text{ms} - 25\text{ms}$ (độc lập với độ dài câu trả lời) |
| **Chi phí vận hành** | Đắt (tính theo triệu token input/output, tiêu tốn KV Cache) | Cực rẻ (thấp hơn $200\times - 400\times$, $0.042 / 1k decisions) |
| **Tính tất định** | Nhạy cảm với prompt phrasing, trôi dạt chú ý (attention drift) | Tất định $100\%$ trên không gian nhãn, không phụ thuộc chat template |
| **Hiệu chuẩn niềm tin** | Khó hiệu chuẩn (LLM thường quá tự tin ngay cả khi hallucinate) | Có sẵn trường **Calibrated Confidence Score** (0.0 – 1.0) |

### 2.2. Ba Hình Thái Quyết Định Có Kiểu (Typed Decisions)
Jev không cho phép mô hình "nói chuyện", mà chỉ chấp nhận 3 loại giao thức đầu ra:
1. **Choice**: Phân loại đối tượng vào một trong $N$ nhãn thuộc tập đóng đã biết trước (ví dụ: `Intent: [EXACT, COMPLEX, SEMANTIC]`).
2. **Score**: Chấm điểm thực thể trên thang đo số học liên tục hoặc rời rạc có rubric rõ ràng (ví dụ: Chấm điểm chất lượng thông điệp từ 1 đến 5).
3. **Noul (Boolean / Binary Gate)**: Quyết định đúng/sai kèm xác suất calibrated (ví dụ: *"Đoạn văn này có chứa trích dẫn luật trực tiếp không?"* $\to$ True với xác suất 0.94).

### 2.3. Cơ Chế Calibrated Confidence & Ngưỡng Fallback
Jev áp dụng kỹ thuật hiệu chuẩn xác suất (tương tự Platt Scaling / Temperature Scaling trên lớp logit cuối). Khi một quyết định có confidence score nằm dưới ngưỡng an toàn (ví dụ: $< 0.80$):
$$\text{Confidence}(x) < \tau_{\text{safe}} \implies \text{Route to System Two (Reasoning LLM) or HITL Queue}$$
Điều này biến System One thành **tấm khiên lọc 90% tải trọng**, chỉ đẩy 10% các trường hợp mơ hồ/biên lên cho các mô hình suy luận đắt đỏ giải quyết.

---

## 3. Mổ Xẻ Thực Nghiệm Tại Rippling (GrowthOS)

### 3.1. Case Thắng Vang Dội: Phân Loại Chất Lượng Outreach (90% vs 50%)
Tại Rippling, nhóm GTM xây dựng bộ tiêu chí chấm điểm chất lượng email/tin nhắn tiếp cận khách hàng.
- **LLM Baseline (Prompted Frontier LLM)** chỉ đạt **50% accuracy** (ngang ngửa tung đồng xu ngẫu nhiên).
  - *Nguyên nhân cốt lõi*: LLM sinh từ bị phân tán sự chú ý vào ngữ cảnh bên lề, cố gắng suy diễn các hàm ý văn chương không có thật, và dễ bị trôi ranh giới phân loại khi prompt dài. Ngoài ra, LLM tiêu tốn phần lớn compute vào việc sinh từ nối và giải thích thay vì tập trung tính toán ranh giới quyết định.
- **Jev** đạt **90% accuracy** và chạy **nhanh hơn gần 8 lần**:
  - Do được huấn luyện trực tiếp trên ranh giới phân loại đóng với hàm mất mát chuyên biệt, toàn bộ năng lượng tính toán của mạng transformer được dồn vào việc ánh xạ input sang không gian nhãn.

### 3.2. Case Thất Bại: Vòng Lặp Text-to-SQL Agent
Khi John Kutay đưa Jev vào làm chốt chặn kiểm soát (control mechanism) cho Text-to-SQL:
- *Bài toán đặt ra*: Câu hỏi không chỉ dừng ở bề mặt *"Truy vấn SQL có trả về dữ liệu không?"*, mà là *"Các dòng dữ liệu này có thực sự khớp với định nghĩa chuẩn tắc (canonical definition) của pipeline hợp lệ tại Rippling không?"*.
- *Lý do Jev thất bại*: Để biết một dòng dữ liệu có phải là "Qualified Pipeline" hay không, hệ thống bắt buộc phải:
  1. Kiểm tra mô hình quan hệ bảng (Data Models & Schemas).
  2. Phân tích các bộ lọc logic lồng nhau (Where clauses, status codes).
  3. Suy luận đối chiếu với tài liệu quy ước kinh doanh nội bộ.
  Đây là **bài toán thu thập ngữ cảnh và suy luận logic nhiều bước (System Two)**. Một mô hình phản xạ System One không có không gian tư duy CoT (Chain-of-Thought) sẽ hoàn toàn bất lực trước các định nghĩa kinh doanh phức tạp này.

### 3.3. Nguyên Lý DRY(E): Evergreen RAG vs Ad-hoc Zero-Embedding RAG
John Kutay đúc kết nguyên lý kiến trúc: **DRY(E) — Don't Repeat Your Embeddings**.

```
                   ┌────────────────────────────────────────┐
                   │    BẢN ĐỒ CHIẾN LƯỢC TRUY XUẤT RAG    │
                   └───────────────────┬────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
   [EVERGREEN RETRIEVAL]                                  [AD-HOC RETRIEVAL]
  (Kho tri thức ổn định, lặp lại)                        (Dữ liệu động, câu hỏi 1 lần)
            │                                                     │
 1. Chunking văn bản một lần                             1. KHÔNG sinh vector embeddings
 2. Sinh Embeddings một lần                              2. Lọc ứng viên nhanh (BM25 / Metadata)
 3. Nạp vào Milvus Vector Index                          3. Đưa tập nhỏ (30-50 chunks) vào
 4. Hàng triệu queries tái sử dụng vector                   System One Scorer tính điểm trực tiếp
            │                                                     │
    "Embed Once ──► Retrieve Many"                           "Zero Embedding Pipeline"
```

1. **Evergreen Case**: Áp dụng cho các kho dữ liệu khổng lồ, ổn định (như hàng triệu cuộc hội thoại bán hàng tại Rippling, hoặc toàn bộ hệ thống văn bản pháp luật QCVN/TCVN tại CCBA). Bắt buộc phải nhúng vector một lần duy nhất vào cơ sở dữ liệu vector.
2. **Ad-hoc Case (Ý tưởng từ @Vtrivedy10)**: Khi cần tìm kiếm trên một tập tài liệu tạm thời, ngắn hạn (ví dụ: các điều khoản trong 1 hợp đồng vừa upload, một cửa sổ nhật ký trace 1 giờ vừa qua): Việc dựng pipeline sinh embedding và tạo vector index là thừa thãi và chậm chạp. Giải pháp tối ưu: **Dùng bộ lọc từ khóa/cấu trúc để lấy 30–50 ứng viên, rồi dùng mô hình System One chấm điểm độ liên quan trực tiếp**.

---

## 4. Đối Chiếu Thực Tế Hệ Thống DGX Spark & Nền Tảng CCBA

Rà soát trực tiếp codebase `dgx-spark-toolkit` trên máy chủ DGX Spark (NVIDIA Grace Blackwell GB10), Grok 4.7 và Antigravity đã phát hiện một sự lệch pha kiến trúc quan trọng:

### 4.1. Điểm Nghẽn Hiện Tại: "Đốt" System Two Cho Việc Của System One
Tại tệp `services/rag-service/retrieval/search_pipeline.py`:
- Hàm `stage1_fast_batch_rerank` đang gom tối đa 30 đoạn văn bản (mỗi đoạn cắt 250 ký tự), gửi lên `claude-haiku-4` (với timeout 4s và fallback về `rag-core` Qwen 35B FP8 cục bộ) để yêu cầu mô hình **sinh chuỗi JSON chứa danh sách `top_indices`**.
- **Hậu quả**:
  1. *Lãng phí compute*: Bắt một mô hình LLM 35 tỷ tham số sinh từ ngữ để làm một phép sắp xếp thứ tự đơn giản.
  2. *Độ trễ cao*: Thời gian gọi LLM + parse JSON mất từ $800\text{ms} - 4000\text{ms}$, có nguy cơ timeout hoặc parse error.
  3. *Tranh chấp slot giải mã trên GPU GB10*: Chiếm dụng bộ nhớ và luồng tính toán vốn cần ưu tiên cho việc sinh câu trả lời pháp lý chuyên sâu.

### 4.2. Sức Mạnh Bị Bỏ Quên: `bge-reranker-v2-m3` Đang Thường Trực Trên GPU
Trong khi đó, tại `retrieval/reranker.py`, chúng ta đã nạp sẵn **`BAAI/bge-reranker-v2-m3`** trên GPU:
- Kiến trúc Cross-Encoder đọc đồng thời `(Query, Passage)`.
- Hỗ trợ ngữ cảnh 1500 ký tự, xử lý batch 32 cực nhanh.
- Cho ra trực tiếp điểm số tương quan số học (Logit) mà **không sinh bất kỳ token chữ nào**.
- **Đây chính là một mô hình System One hoàn hảo đã có sẵn trong hệ thống!**

---

## 5. Bản Đồ 6 Bài Toán System One Trong Hệ Sinh Thái Pháp Lý CCBA

Thay vì sử dụng các LLM sinh từ tự do cho các tác vụ trung gian, hệ sinh thái CCBA / DGX Spark cần phân tầng rạch ròi 6 bài toán System One:

```
[NGƯỜI DÙNG / AGENT REQUEST]
             │
             ▼
   [TẦNG 0: CODE & REGEX TẤT ĐỊNH] ──────► Số hiệu văn bản, ngày ban hành, điều khoản cụ thể
             │ (Nếu là câu hỏi ngữ nghĩa)
             ▼
   [TẦNG 1: SYSTEM ONE (Reflex Models)]
   ├── 1. Reranker: BGE-Reranker-v2-m3 chấm điểm ứng viên hybrid search (Zero JSON generation)
   ├── 2. Intent Classifier: Phân luồng câu hỏi (EXACT, COMPLEX, SEMANTIC)
   ├── 3. Citation Validator: Noul Boolean gate kiểm tra (Claim, Source Chunk)
   ├── 4. Maskara Guard: Phân loại token nhạy cảm (API Keys, Passwords, PII)
   ├── 5. Atomic Predicates: "Điều khoản này có quy định trị số kỹ thuật không?"
   └── 6. QC BIM Classifier: Gán nhãn lỗi mô hình theo taxonomy đóng
             │
             ▼ (Chỉ khi cần tổng hợp, suy luận mâu thuẫn hoặc giải thích sâu)
   [TẦNG 2: SYSTEM TWO (Reasoning LLMs - Qwen 3.6 35B / Claude Opus / Gemini Pro)]
```

| STT | Bài toán nghiệp vụ CCBA | Hình thái System One | Giải pháp công nghệ khuyến nghị trên DGX Spark |
|:---:|---|:---:|---|
| **1** | **Xếp hạng ứng viên RAG** | **Score** | Dùng `bge-reranker-v2-m3` thay thế hoàn toàn `stage1_fast_batch_rerank` của Haiku/Qwen. |
| **2** | **Xác thực trích dẫn (Footnote Validation)** | **Noul** (True/False) | Chấm điểm tương quan chéo giữa câu khẳng định (claim) và đoạn trích luật. Nếu score $< 0.75 \to$ loại bỏ footnote ảo. |
| **3** | **Phân loại lỗi hồ sơ QC BIM** | **Choice** | Phân loại lỗi bản vẽ vào taxonomy chuẩn mực (Kiến trúc, Kết cấu, MEP) theo danh mục đóng. |
| **4** | **Phát hiện dữ liệu nhạy cảm (Maskara)** | **Choice + Score** | Nhận diện Secret Key, Connection String với độ tự tin hiệu chuẩn; nếu nghi ngờ $\to$ chuyển hàng đợi HITL (Redis DB 4). |
| **5** | **Định tuyến ý định truy vấn (Query Intent)** | **Choice** | Phân loại nhanh câu hỏi: Tra cứu số hiệu $\to$ Fast Lookup; Phân tích tranh chấp $\to$ Agentic Pipeline. |
| **6** | **Kiểm tra vị từ pháp lý nguyên tử** | **Noul** | Trả lời nhanh: *"Văn bản này có bị sửa đổi bởi văn bản nào khác trong state không?"*. |

---

## 6. Vấn Đề Tiếng Việt & Độc Lập Hạ Tầng (Sovereignty)

- **Về mô hình Jev của TypeSafe**:
  - Jev là dịch vụ API đám mây thương mại đóng (closed-source, SaaS).
  - Hiện chưa có bất kỳ bài đánh giá chuẩn (benchmark) công khai nào về khả năng hiểu tiếng Việt và cấu trúc văn bản hành chính Việt Nam (Điều/Khoản/Điểm lồng nhau, viện dẫn chéo).
  - Dữ liệu hồ sơ dự án, quy chuẩn kỹ thuật và tài liệu thiết kế xây dựng không nên gửi ra ngoài biên giới máy chủ qua một API đóng chưa được kiểm chứng.
- **Giải pháp Tương đương System One Cục Bộ trên DGX Spark GB10**:
  1. **BGE-M3 & BGE-Reranker-v2-m3**: Huấn luyện trên tập ngữ liệu đa ngôn ngữ khổng lồ (>100 ngôn ngữ), xử lý tiếng Việt cực kỳ chuẩn xác, chạy 100% offline trên GPU GB10.
  2. **Qwen 3.6 35B với chế độ `enable_thinking: False` (`local-instruct`)**: Đóng vai trò bộ phân loại cấu trúc JSON siêu tốc (~0.2s) mà không bị token starvation.
  3. **PhoBERT / ViDeBERTa**: Dành riêng cho các tác vụ phân loại thực thể ngắn (Named Entity Recognition cho số hiệu công văn, tên cơ quan ban hành).

---

## 7. Khuyến Nghị Hành Động (Actionable Roadmap)

1. **Khử Bỏ System Two Trên Hot Path Truy Xuất**:
   - Refactor `retrieval/search_pipeline.py`: Xóa bỏ việc gọi `claude-haiku-4` / `rag-core` để sinh JSON index trong `stage1_fast_batch_rerank`.
   - Kết nối trực tiếp kết quả từ `retrieval/reranker.py` (`bge-reranker-v2-m3`) làm tầng lọc duy nhất trước khi tổng hợp context.
2. **Áp Dụng Nguyên Lý DRY(E)**:
   - Duy trì nguyên tắc *Embed Once $\to$ Retrieve Many* cho kho dữ liệu luật pháp điển (`legal_docs_v11` trên Milvus).
   - Với các tác vụ ad-hoc tạm thời (so sánh 2 văn bản cá biệt do người dùng tải lên trong phiên chat): Không tạo collection mới trong Milvus, mà đưa thẳng danh sách đoạn cắt vào `bge-reranker-v2-m3` để lấy top k liên quan nhất.
3. **Thiết Lập Chốt Chặn Xác Thực Trích Dẫn Bằng Noul Scorer**:
   - Trước khi trả về câu trả lời cho kỹ sư, chạy một vòng kiểm tra Noul (Cross-Encoder score) giữa từng câu viện dẫn và điều luật trích dẫn tương ứng để triệt tiêu 100% lỗi ảo giác số hiệu điều khoản.
