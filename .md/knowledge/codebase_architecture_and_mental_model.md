# BÁO CÁO TOÀN DIỆN: MENTAL MODEL VÀ KIẾN TRÚC TỔNG THỂ DGX-SPARK-TOOLKIT

**Hệ thống**: dgx-spark-toolkit — Nền tảng Vietnamese Legal Document RAG trên NVIDIA DGX Spark (Blackwell GB10, 128GB Unified Memory)  
**Thời gian kiểm chứng**: 2026-09-24  
**Phương pháp**: Double-Pass Adversarial Review & Live Measurement trên cụm máy chủ DGX Spark  

---

## 1. TỔNG QUAN PHẢN BIỆN KỸ THUẬT (ADVERSARIAL AUDIT & CORRECTIONS)

Qua quá trình rà soát mã nguồn trực tiếp kết hợp kiểm thử thực nghiệm trên các dịch vụ đang chạy live, hệ thống ghi nhận các phát hiện kỹ thuật cốt lõi và hiệu chỉnh:

| Vấn đề | Chi tiết mã nguồn & Dữ liệu thực tế | Phân tích & Ý nghĩa kiến trúc |
| :--- | :--- | :--- |
| **Phân loại Intent** | [`retrieval/query_classifier.py:21-25`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/query_classifier.py#L21-L25): Enum `QueryIntent` định nghĩa chính thức là `EXACT`, `COMPLEX`, và **`SEMANTIC`** (hoàn toàn không có `GENERAL`). | Classifier chạy bằng Regex thuần túy (0ms LLM latency) chia luồng: `EXACT` (BM25 ưu tiên số hiệu văn bản), `COMPLEX` (Multi-hop Agentic), và `SEMANTIC` (Hybrid cân bằng BGE-M3). |
| **Quan hệ Pháp lý** | [`ingestion/models.py:137-151`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/models.py#L137-L151): `DocumentRelationships` gồm **4 quan hệ**: `replaces`, `amends`, `references`, và **`guides`**. | Bổ sung quan hệ `guides` (hướng dẫn thi hành) là trục quan trọng trong hệ thống văn bản quy phạm pháp luật Việt Nam (Luật -> Nghị định -> Thông tư). |
| **SSE Stream Client** | [`services/frontend/src/lib/streamClient.ts`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/frontend/src/lib/streamClient.ts) triển khai `StreamClient` với tự phục hồi kết nối và fallback REST. | Mã nguồn thực tế đồng bộ là `streamClient.ts` (tài liệu [ARCHITECTURE.md](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/ARCHITECTURE.md) trước đó có drift ghi `streamApi.ts`). |
| **vLLM Blackwell GB10** | Container `qwen36b` chạy image `vllm/vllm-openai:latest` phục vụ `Qwen3.5-35B-A3B-FP8` với 96k context window trên cổng 8004. | Đo thực tế: Thời gian tạo 10 token đạt **0.298s (298ms)** (~33.5 tok/s). |
| **Centralized API Proxy** | Kết nối Tailscale VPN tới `http://100.83.192.30:8045/v1`. | Đo thực tế: SLA latency đạt **71.7ms**, quản lý **31 models** sẵn sàng phục vụ. |
| **Quy mô Vector & Graph** | Truy vấn live từ [`api/routers/stats.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/api/routers/stats.py): Collection `legal_docs_v11`. | Milvus: **4,051 entities** (45.7% so với baseline 8,870 target); Neo4j: **19 documents**, **12 relationships**. |
| **Cơ chế Warmup Model** | [`core/warmup.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/core/warmup.py) kết hợp `_warmup_thread_lock` và `asyncio.shield`. | Tránh lỗi 503 degraded khi biên dịch CUDA/PyTorch cold embedding trên GB10; thời gian khởi động đo thực tế là **89.08 giây** (khớp với PITFALLS.md yêu cầu timeout >= 110s). |

---

## 2. BẢY (07) TRỤ CỘT MENTAL MODEL CỐT LÕI

### 2.1. Mental Model 1: "Deep Seams Over Shallow Abstractions" (Kiến trúc Module Sâu)
Codebase triệt để tuân thủ triết lý của John Ousterhout: **Giao diện mỏng nhưng chức năng sâu rộng**.
- **`DocumentIngestionPipeline`** ([`ingestion/pipeline.py:85`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py#L85)): Điểm vào duy nhất `run_pipeline(file_path)` tự đóng gói toàn bộ 9 stage: Intake -> OCR -> Metadata Extraction -> Identity Resolution -> Chunking -> Enrichment -> Embedding -> Indexing -> Export.
- **`DocumentReader`** ([`ingestion/document_reader.py:64`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/document_reader.py#L64)): Một API duy nhất `extract(file_path)` tự động xử lý định dạng PDF native, scanned PDF (Surya/Cloud Vision OCR), Word (`.doc`, `.docx`), Excel (`.xls`, `.xlsx`), và Image.
- **`DocumentStore`** ([`repositories/document_store.py:33`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/repositories/document_store.py#L33)): Quản trị giao dịch nguyên tử phân tán trên 3 database (Milvus, Neo4j, PostgreSQL), đảm bảo tính nhất quán dữ liệu vòng đời.
- **`SearchPipeline`** ([`retrieval/search_pipeline.py:216`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/search_pipeline.py#L216)): Gói gọn quy trình truy vấn: Cache -> Intent Classification -> Multi-Hop -> Hybrid Search -> Rerank -> Parent-Child Context Expansion -> Graph Timeline.

### 2.2. Mental Model 2: "Hierarchical Legal Chunking with Context Inheritance"
Khác với RAG thông thường cắt đoạn theo số lượng token cố định:
- **6 chiến lược cắt văn bản có thứ tự ưu tiên**: `LayoutAwareChunker` -> `VietLawArticleChunker` -> `VietLawNumberedSectionChunker` -> `VietLawSectionChunker` -> `FormFieldChunker` -> `GenericFallbackChunker`.
- **Kế thừa ngữ cảnh (Context Inheritance)**: Mỗi Điều (Article) được tiền tố hóa ngữ cảnh Phần/Chương/Mục cha ngay trong nội dung: `[Chương II: QUYỀN VÀ NGHĨA VỤ] ::: Điều 15...` giúp embedding mang đầy đủ ngữ cảnh dù nằm ở vị trí sâu.
- **Multimodal Table Healing & Table Summary**: Bảng biểu vỡ cấu trúc được phục hồi bằng mô hình Vision; bảng dài (>2000 ký tự) tự sinh thêm chunk tóm tắt `chunk_type: table_summary` để cải thiện khả năng trúng khớp tổng quan.
- **Parent-Child Context Expansion** ([`search_pipeline.py:578`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/search_pipeline.py#L578)): Khi tìm kiếm, Milvus trả về chunk con (Khoản chi tiết). SearchPipeline tự tra ngược để lấy toàn bộ Điều cha cung cấp cho LLM, bảo toàn tính toàn vẹn của điều luật.

### 2.3. Mental Model 3: "Bi-Temporal Legal Validity & Graph Truth Oracle"
- **Xung đột hiệu lực**: Văn bản pháp luật cũ và mới có độ tương đồng ngữ nghĩa cực cao (dễ gây hallucination nếu chỉ dựa vào Vector Search).
- **Neo4j là Trọng tài Hiệu lực (Truth Oracle)**: Quản lý 4 quan hệ pháp lý: `REPLACES`, `AMENDS`, `REFERENCES`, `GUIDES`.
- **Chấm điểm Hybrid kết hợp Trạng thái Pháp lý** ([`search_pipeline.py:553`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/search_pipeline.py#L553)):
  $$\text{Score} = (\text{Score}_{\text{rerank}} \times 0.8) + (\text{Score}_{\text{milvus}} \times 0.2) + \text{TableBoost} + \text{ValidityBoost}$$
  Văn bản `ACTIVE` được cộng điểm ưu tiên, văn bản `OUTDATED` chịu phạt điểm. Khi trúng văn bản đã hết hiệu lực, hệ thống tự động duyệt đồ thị Neo4j và chèn tiền tố `[LEGAL TIMELINE]: ...` cảnh báo LLM.

### 2.4. Mental Model 4: "Multi-Hop Agentic Plan-Retrieve-Reflect Loop"
Xử lý các câu hỏi phức tạp (`QueryIntent.COMPLEX`) qua vòng lặp tự trị ([`search_pipeline.py:423-514`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/search_pipeline.py#L423-L514)):
1. **Plan**: Phân rã câu hỏi ban đầu thành tối đa 3 sub-queries độc lập.
2. **Hop 1 Retrieval**: Thực thi song song qua `asyncio.gather` trên Milvus, hợp nhất và deduplicate.
3. **Reflect**: LLM đánh giá độ đủ của ngữ cảnh (`is_sufficient: bool`, `confidence: float`).
4. **Hop 2 Retrieval**: Nếu chưa đủ thông tin, tự động tạo câu hỏi bổ trợ (`follow_up_query`) và thực hiện đợt tìm kiếm thứ hai trước khi tổng hợp câu trả lời.

### 2.5. Mental Model 5: "Dual-Engine Staircase & 3-Tier AI Gateway Topology"
Kiến trúc định tuyến mô hình thông minh giảm thiểu chi phí và tăng tính sẵn sàng:
- **Tier 1 (Google AI Studio Free Pool)**: 10 API keys xoay vòng, cung cấp 144k request/ngày phục vụ OCR thị giác và trích xuất thực thể nhanh.
- **Tier 2 (Centralized API Proxy - Tailscale VPN `100.83.192.30:8045`)**: Định tuyến các mô hình reasoning cao cấp (Claude 3.7/Sonnet 4.6 Thinking, GPT-4o, Gemini 3.5 Flash High) qua chuẩn OpenAI format.
- **Tier 3 (Local On-Prem GPU Safety Net)**: Khi mất kết nối ngoài hoặc cạn quota, hệ thống tự động fallback về `rag-core` (Qwen 35B FP8 trên Blackwell GB10 local).
- **Callbacks bảo vệ chủ động** ([`custom_callbacks.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/custom_callbacks.py)): `KeyCooldownManager` tự động cách ly key dính HTTP 429 trong 60 giây; `ParameterNormalizer` chuyển đổi ngân sách suy nghĩ phù hợp với từng mô hình.

### 2.6. Mental Model 6: "Penta-Partitioned Memory & Context Lake"
Phân tách bộ nhớ Redis thành 5 database riêng biệt nhằm tránh xung đột namespace:
- **Redis DB 0**: Semantic Cache của LiteLLM Proxy (ngưỡng cosine similarity >= 0.85).
- **Redis DB 1**: Ingestion Queue (`ingest:queue`), Ingestion Concurrency Lock, Table Cache.
- **Redis DB 2 (Context Lake)**:
  - `SessionMemory` ([`retrieval/session_memory.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/session_memory.py)): Lưu trữ 20 lượt chat gần nhất (TTL 2 giờ).
  - `TraceStore` ([`retrieval/query_tracer.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/query_tracer.py)): Lưu vết từng bước suy luận RAG (circular buffer tối đa 500 traces).
  - `ContextAccumulator` ([`retrieval/context_accumulator.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/context_accumulator.py)): Tích lũy tài liệu qua các lượt hội thoại với hệ số suy giảm (decay factor 0.8).
- **Redis DB 3**: `SemanticCache` L2 persistent cache ([`retrieval/semantic_cache.py:52`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/semantic_cache.py#L52)).
- **Redis DB 4**: `HITLService` low-confidence review queue ([`services/hitl_service.py:79-83`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/services/hitl_service.py#L79-L83)).

### 2.7. Mental Model 7: "Zero-Ingress ChatOps & Karpathy Autoresearch"
- **Zero-Ingress ChatOps** ([`scripts/chatops_daemon.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/scripts/chatops_daemon.py)): Điều hành máy chủ qua Telegram Bot bằng cơ chế Long-polling, không mở bất kỳ port nào ra Internet; có chuỗi kiểm toán bảo mật Chained SHA-256 Audit Trail.
- **Smart Watchdog** ([`scripts/smart_watchdog.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/scripts/smart_watchdog.py)): Lắng nghe Docker events qua local socket để tự động cảnh báo và hồi phục dịch vụ.
- **Karpathy-style Autoresearch** ([`services/rag-service/autoresearch/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/autoresearch/)): Vòng lặp cải tiến RAG tự trị, Agent tự tinh chỉnh `optimize_rag.py` và chấm điểm 5 chiều (Markdown, JSON, Chunking, Milvus, PDF-MD Fidelity).

---

## 3. SƠ ĐỒ LUỒNG DỮ LIỆU END-TO-END

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 NVIDIA DGX SPARK (GB10 BLACKWELL 128GB)                                 │
│                                                                                                        │
│  [ CLIENT LAYER ]                                                                                      │
│   React 19 SPA (:5173) ──(REST / SSE Stream)──┐                                                        │
│   Telegram Bot (Long-polling 0-ingress) ──────┼───┐                                                    │
│                                               ▼   ▼                                                    │
│  [ APPLICATION & RETRIEVAL LAYER ]                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ RAG Service FastAPI (:8005) [Python 3.12, Async]                                                 │  │
│  │  ├── Query Classifier (EXACT, COMPLEX, SEMANTIC) ──> Semantic Cache Check (Redis DB 0)           │  │
│  │  ├── Multi-Hop Agentic Loop (Plan ──> Retrieve Hop 1 ──> Reflect ──> Retrieve Hop 2)              │  │
│  │  ├── Hybrid Retrieval (Dense 1024d + Sparse Lexical BGE-M3 via Milvus)                           │  │
│  │  ├── 2-Stage Reranker (Stage 1 Fast Filter + Stage 2 Cross-Encoder Local GPU)                    │  │
│  │  ├── Parent-Child Expansion (Child chunk ──> Fetch Parent Điều ──> Expand Context)               │  │
│  │  ├── Graph RAG Timeline (Neo4j Status Check ──> REPLACES Traversal ──> Prefix Timeline)          │  │
│  │  └── Business Services: ChatService, LegalAnalysisEngine, ComplianceService, HitlService         │  │
│  └──────────────────┬─────────────────┬─────────────────┬──────────────────┬────────────────────────┘  │
│                     │                 │                 │                  │                           │
│  [ DATA & PERSISTENCE LAYER ]         │                 │                  │                           │
│  ┌───────────────┐  │ ┌────────────┐  │ ┌────────────┐  │ ┌─────────────┐  │                           │
│  │ Milvus        │◄─┘ │ Neo4j      │◄─┘ │ PostgreSQL │◄─┘ │ Redis 7     │◄─┘                           │
│  │ (:19530)      │    │ (:7687)    │    │ (:5432)    │    │ (:6379)     │                              │
│  │ Hybrid Dense  │    │ Knowledge  │    │ Ingestion  │    │ DB 0: Cache │                              │
│  │ + Sparse BM25 │    │ Graph:     │    │ State &    │    │ DB 1: Queue │                              │
│  │ legal_docs_v11│    │ REPLACES/  │    │ LiteLLM    │    │ DB 2: Lake  │                              │
│  │ (4,051 chunks)│    │ AMENDS/    │    │ Token Logs │    │ (Session &  │                              │
│  │               │    │ REFERENCES/│    │            │    │  Traces)    │                              │
│  │               │    │ GUIDES     │    │            │    │             │                              │
│  └───────────────┘    └────────────┘    └────────────┘    └─────────────┘                              │
│                                                                                                        │
│  [ INGESTION WORKER LAYER ]                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ rag-watcher (Worker Daemon)                                                                      │  │
│  │  s01_intake ──> s02_ocr (Surya / Cloud Vision) ──> s03_metadata ──> s04_identity (Canonical ID)  │  │
│  │  ──> s05_chunking (Context Inheritance & Table Repair) ──> s06_enrichment (4 Relations)          │  │
│  │  ──> s07_embedding (BGE-M3) ──> s08_indexing (Milvus + Neo4j) ──> s09_export (JSON + Markdown)   │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                        │
│  [ AI GATEWAY & INFERENCE ROUTING LAYER ]                                                               │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ LiteLLM Proxy (:8090 / :4000)                                                                    │  │
│  │  ├── Callbacks: KeyCooldownManager (60s lock on 429), ParameterNormalizer (thinking mapping)      │  │
│  │  ├── Tier 1: Google AI Studio Direct (10 API Keys Pool, 7,000 trang OCR free/ngày)               │  │
│  │  ├── Tier 2: Centralized API Proxy (Tailscale 100.83.192.30:8045 - Claude, GPT-4o, Gemini High) │  │
│  │  └── Tier 3: Local vLLM Inference (qwen36b: Qwen3.5-35B-FP8, 96K context, 75% GPU Memory)        │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. MA TRẬN PHÂN HỆ VÀ TRÁCH NHIỆM TRONG CODEBASE

| Phân hệ | Thành phần chính | Vị trí mã nguồn | Trách nhiệm và Cơ chế vận hành |
| :--- | :--- | :--- | :--- |
| **Ingestion Pipeline** | `DocumentIngestionPipeline`, `DocumentReader`, `DocumentChunker` | [`services/rag-service/ingestion/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/) | 9-stage intake, kế thừa ngữ cảnh Chương/Mục vào từng Điều, Vision repair bảng vỡ, trích xuất 4 loại quan hệ pháp lý. |
| **Ingestion Queue** | `IngestionQueue`, `RedisQueue`, `StateManager` | [`services/rag-service/ingestion/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/) | Redis Streams DB 1 (`ingest:queue`), switch ngắt khẩn cấp `rag:ingestion:paused`, claim lock nguyên tử trên PostgreSQL. |
| **Repositories** | `DocumentStore`, `MilvusRepository`, `Neo4jRepository` | [`services/rag-service/repositories/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/repositories/) | Đồng bộ dữ liệu phân tán giữa Milvus (`legal_docs_v11`), Neo4j và PostgreSQL, băm cryptographic SHA-256 (ADR-0059). |
| **Retrieval Engine** | `SearchPipeline`, `QueryClassifier`, `Reranker` | [`services/rag-service/retrieval/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/) | Regex classifier 0ms, HyDE, Hybrid Dense + Sparse BM25 BGE-M3, 2-stage rerank, Parent-Child expansion, Graph timeline. |
| **Context Lake** | `SessionMemory`, `TraceStore`, `ContextAccumulator` | [`services/rag-service/retrieval/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/) | Redis DB 2 độc lập: lưu trữ 20 turns hội thoại (TTL 2h), traces suy luận từng bước (TTL 24h), tích lũy tài liệu có hệ số decay 0.8. |
| **AI Gateway** | LiteLLM Proxy, `custom_callbacks.py`, `AIGatewayClient` | [`services/ai-gateway/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/), [`core/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/core/) | Định tuyến 3 tầng (Cloud Free -> Centralized Proxy -> Local GPU), cách ly key 429 60s, chuẩn hóa tham số thinking cho Gemini 3.x. |
| **Warmup Engine** | `core/warmup.py` | [`services/rag-service/core/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/core/) | Khởi động tuần tự BGE-M3 và Cross-Encoder, tự chữa lành qua `asyncio.shield`, chống deadlock mutex khi container boot trên GB10. |
| **Business Services** | `ChatService`, `LegalAnalysisEngine`, `ComplianceService` | [`services/rag-service/services/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/services/) | Trích dẫn nguồn bounding box, phân tích delta (so sánh văn bản cũ - mới), thẩm định hồ sơ công trình (Compliant, Risks, Violations). |
| **Frontend Web** | React 19, Tailwind 4, `StreamClient`, `react-force-graph-2d` | [`services/frontend/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/frontend/) | UI thời gian thực, SSE streaming tự phục hồi, hiển thị đồ thị quan hệ văn bản pháp lý 2D Canvas (HTML5). |
| **ChatOps & Ops** | `chatops_daemon.py`, `smart_watchdog.py` | [`scripts/`](file:///home/vvc/Codebase/dgx-spark-toolkit/scripts/) | Bot Telegram Long-polling (0 open ports), mã hóa kiểm toán SHA-256 audit log, mã PIN cứu hộ khẩn cấp, giám sát Docker daemon. |
| **Autoresearch** | `program.md`, `prepare.py`, `optimize_rag.py` | [`services/rag-service/autoresearch/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/autoresearch/) | Vòng lặp tối ưu hóa pipeline RAG tự trị (Karpathy-style) đánh giá 5 chiều chất lượng (Markdown, JSON, Chunking, Milvus, Fidelity). |

---

## 5. CÁC ĐIỂM CẦN LƯU Ý CHO PHÁT TRIỂN TIẾP THEO

1. **Tiến độ Ingestion Dữ liệu**: Milvus hiện có 4,051 chunks / 8,870 target (~45.7%). Cần duy trì theo dõi hàng đợi `ingest:queue` để hoàn tất khối tài liệu văn bản quy phạm pháp luật còn lại.
2. **Đồng bộ Tài liệu (Documentation Sync)**: [ĐÃ HOÀN TẤT] Đã cập nhật đồng bộ toàn diện `docs/ARCHITECTURE.md`, `.github/copilot-instructions.md`, và `.github/instructions/frontend-react.instructions.md` (`streamClient.ts`, `legal_docs_v11`, quan hệ `GUIDES`, `Redis DB 2 Context Lake`, container `vllm-36b` 96k context).
3. **Cân bằng Tải VRAM GB10**: `qwen36b` chiếm 75% GPU Memory (~78GB). Khi chạy batch OCR với Surya, cần đảm bảo điều phối qua CPU hoặc Cloud Vision để tránh tranh chấp bộ nhớ thống nhất (Unified Memory).
