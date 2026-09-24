# BIÊN BẢN QUYẾT ĐỊNH THIẾT KẾ: ĐỒNG BỘ HÓA DOCUMENTATION DRIFT
(CCBA Grilling Decision Log & Resolution Summary)

**Dự án**: `dgx-spark-toolkit`  
**Thời gian hoàn thành**: 2026-09-24  
**Chế độ thực thi**: `ccba-grilling` (Frontier Decision Loop & Resolution)  

---

## 1. BỐI CẢNH & PHÁT HIỆN LỆCH TÀI LIỆU (DRIFT CONTEXT)

Trong quá trình đối soát và kiểm chứng mã nguồn thực tế đối chiếu với các tài liệu quy chuẩn (`docs/ARCHITECTURE.md`, `.github/copilot-instructions.md`, `.github/instructions/frontend-react.instructions.md`), hệ thống ghi nhận các sai lệch tài liệu kỹ thuật phát sinh sau các đợt refactor:
1. **Frontend Streaming Client**: Refactor tầng giao diện đã hợp nhất và xóa bỏ `streamApi.ts`, chuyển toàn bộ logic SSE sang `StreamClient` tại `services/frontend/src/lib/streamClient.ts`.
2. **Milvus Collection**: Hệ thống đã nâng cấp từ collection `legal_docs_v9` lên `legal_docs_v11` (xác nhận trong `core/config.py` và stats live: 4,051 entities).
3. **Neo4j Relationships**: Thiếu quan hệ pháp lý `GUIDES` (hướng dẫn thi hành) trong bảng định nghĩa quan hệ.
4. **Redis Partitioning**: Thiếu định nghĩa `Redis DB 2: Context Lake` (quản lý `SessionMemory`, `TraceStore`, `ContextAccumulator`).
5. **vLLM Service Container**: Tài liệu ghi `vllm-35b` với 32k context, trong khi thực tế cấu hình `docker-compose.yml` và runtime live là container `qwen36b` (service `vllm-36b`) với model Qwen3.5-35B-FP8 và 96k context window (98,304 tokens).

---

## 2. QUÁ TRÌNH HỘI TỤ QUYẾT ĐỊNH (FRONTIER RESOLUTIONS)

*   **Quyết định 1 (Phạm vi xử lý Drift)**:
    *   *Các phương án đối chiếu*:
        *   Phương án 1 (Đề xuất): Đồng bộ hóa toàn diện cả `docs/ARCHITECTURE.md` và các quy chuẩn hướng dẫn trong `.github/`.
        *   Phương án 2: Chỉ sửa trong `docs/ARCHITECTURE.md`.
        *   Phương án 3: Sửa tối thiểu đúng 2 vị trí được chỉ định.
    *   *Phán quyết của Người dùng*: **Chấp thuận Phương án 1 (Đồng bộ hóa toàn diện)**.
*   **Quyết định 2 (Kế hoạch thực thi & Kiểm chứng)**:
    *   *Phán quyết của Người dùng*: **Tiến hành chỉnh sửa trực tiếp ngay lập tức** và kiểm thử lint/build để khóa chất lượng.

---

## 3. CÁC TỆP ĐÃ ĐỒNG BỘ HÓA (DIFF MANIFEST)

1.  [`docs/ARCHITECTURE.md`](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/ARCHITECTURE.md):
    *   Dòng 48: Cập nhật tích hợp frontend từ `src/lib/streamApi.ts` thành `src/lib/streamClient.ts` (SSE).
    *   Dòng 56: Cập nhật Milvus collection từ `legal_docs_v9` thành `legal_docs_v11`.
    *   Dòng 57: Bổ sung quan hệ `GUIDES` vào bảng quan hệ Neo4j.
    *   Dòng 59: Bổ sung `Redis DB 2: Context lake (Session & Traces)` vào bảng phân vùng Redis.
    *   Dòng 70: Cập nhật cấu hình model container `vllm-36b` (Qwen3.5-35B-FP8, 78GB memory limit, 96k context).
2.  [`.github/copilot-instructions.md`](file:///home/vvc/Codebase/dgx-spark-toolkit/.github/copilot-instructions.md):
    *   Dòng 18: Cập nhật `vllm-36b` (Qwen3.5-35B-FP8, always-on, 78GB, 96k ctx).
    *   Dòng 23: Cập nhật Milvus collection `legal_docs_v11`.
    *   Dòng 24: Bổ sung quan hệ `GUIDES` cho Neo4j.
    *   Dòng 26: Bổ sung `DB 2: Context Lake` cho Redis.
    *   Dòng 58: Cập nhật API client `api.ts (REST) + streamClient.ts (SSE)`.
3.  [`.github/instructions/frontend-react.instructions.md`](file:///home/vvc/Codebase/dgx-spark-toolkit/.github/instructions/frontend-react.instructions.md):
    *   Dòng 10: Cập nhật `api.ts (REST via axios) + streamClient.ts (SSE streaming with auto fallback)`.
    *   Dòng 15: Cập nhật pattern gọi SSE từ `sendStreamChat()` sang `StreamClient.streamChat()` từ `lib/streamClient.ts`.

---

## 4. KẾT QUẢ KIỂM CHỨNG TỰ ĐỘNG (DETERMINISTIC VERIFICATION)

*   **Backend Linter**: `flake8 services/rag-service/ --config=services/rag-service/.flake8` $\rightarrow$ **Pass (0 errors)**.
*   **Frontend Linter**: `npm run lint` $\rightarrow$ **Pass (0 errors)**.
*   **Frontend Production Build**: `npm run build` $\rightarrow$ **Pass (`built in 5.52s`, Exit code 0)**.
*   **Active Drift Grep**: Không còn bất kỳ tham chiếu lỗi thời nào đến `streamApi` hoặc `legal_docs_v9` trong các tệp tài liệu và quy chuẩn đang hoạt động.
