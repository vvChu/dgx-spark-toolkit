# Ticket [TICK-01]: Khảo sát Hiện trạng & Thiết lập Benchmark Baseline cho Hot-Path Reranker

**Bản đồ cha:** [Bản đồ Định hướng Phân tách Quyết định System One & System Two](../map.md)  
**Phân loại:** `Research [AFK]`  
**Giai đoạn:** Phase 1 (Hot-path Retrieval)  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent (via Research Subagent `6f26fae5`)  
**Ngày hoàn tất:** 29/09/2026  
**Phụ thuộc:** Không có (Unblocked)  

---

## 1. Mục tiêu
Thực hiện khảo sát đối soát mã nguồn và đo lường định lượng hiệu năng thực tế của khâu Rerank hiện tại trong [services/rag-service/retrieval/search_pipeline.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/search_pipeline.py) so với [services/rag-service/retrieval/reranker.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/reranker.py), tạo cơ sở dữ liệu thực nghiệm trước khi thực hiện refactor.

## 2. Kết quả Khảo sát Mã nguồn (`services/rag-service/tests/`)
1. **Tìm kiếm phụ thuộc `stage1_fast_batch_rerank`**:
   - `grep -rn "stage1_fast_batch_rerank" services/rag-service/tests/` $\rightarrow$ **0 kết quả**. Không có test case hay fixture nào gọi, mock hoặc phụ thuộc vào hàm này.
2. **Tìm kiếm phụ thuộc `complete_json`**:
   - Chỉ xuất hiện trong `test_compliance_service.py` và `test_ai_gateway_client.py`. Không có file test nào dùng `complete_json` cho khâu rerank.
3. **Hiện trạng tại `tests/test_search_pipeline.py`**:
   - Các test case hiện tại chỉ mock 1 hit duy nhất (`len(docs) == 1`), chưa từng kích hoạt điều kiện `len(docs) > 60` của hàm cũ.
   - Khâu rerank trong unit tests được mock trực tiếp qua `get_reranker().rerank`.
   - **Kết luận**: Việc xóa bỏ hoàn toàn `stage1_fast_batch_rerank` sẽ **không làm vỡ bất kỳ test case nào hiện có**.

## 3. Lỗ hổng Kiến trúc & Tính Khả thi trong `search_pipeline.py`
1. **Lỗ hổng thiết kế cũ**:
   - Tại dòng 186 của hàm `stage1_fast_batch_rerank`: Mã nguồn cắt `docs[:30]` gửi vào prompt LLM. Nếu candidate set có 60–100 chunks, các chunk từ 31 đến 100 **bị loại bỏ hoàn toàn trong mù quáng**.
2. **Đánh giá rủi ro khi đưa trực tiếp vào `reranker.rerank()`**:
   - *Độ dài chuỗi*: An toàn 100%. `reranker.py` đã có sẵn cơ chế cắt `doc[:1500]`, hoàn toàn nằm gọn trong context window 8192 tokens của BGE-M3.
   - *Bộ nhớ VRAM*: An toàn 100%. `predict(pairs, batch_size=32)` xử lý theo từng mini-batch, VRAM activation chỉ dao động 130MB – 534MB trên nền model 2.16GB.
   - *Hợp đồng dữ liệu*: Giữ nguyên tính toàn vẹn `list[tuple[str, float]]` tương thích với `hit_map.get(doc_text)`.

## 4. Số liệu Benchmark Thực nghiệm Đo trên DGX Spark Blackwell GB10
*(Phần cứng: NVIDIA Grace Blackwell GB10, aarch64, CUDA 13.1, Driver 580.178.04)*

### Bảng đo lường BGE-Reranker-v2-m3 (Batch size = 32, Chunk dài ~1300 ký tự):
| Số lượng chunks ($N$) | Latency trung bình | Latency P95 | Latency Min | Latency Max | VRAM Peak (gồm model) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **$N = 30$ chunks** | **678.77 ms** | **734.02 ms** | 648.05 ms | 734.02 ms | 2,668.3 MB |
| **$N = 60$ chunks** | **1,294.36 ms** | **1,299.81 ms** | 1,288.39 ms | 1,299.81 ms | 2,699.6 MB |
| **$N = 100$ chunks** | **2,162.65 ms** | **2,175.63 ms** | 2,149.00 ms | 2,175.63 ms | 2,699.8 MB |

*(Đối với văn bản ngắn ~500 ký tự, $N=60$ chunks chỉ mất **494.87 ms**).*

### Phản biện Giả thuyết Ban đầu (Self-Adversarial Fact Check):
- **BÁC BỎ giả thuyết $< 50\text{ms}$**: Giả thuyết ban đầu nhầm lẫn giữa Bi-Encoder embedding và Cross-Encoder full-attention. BGE-Reranker-v2-m3 tính cross-attention toàn phần giữa query và chunk qua 24 layers transformer, mất ~21–22ms/chunk trên GB10.
- **So với luồng cũ**: Luồng cũ gọi LLM qua AI Gateway bị timeout mạng/retry mất **~9,550 ms**. Luồng mới với trần 60 chunks mất **~1,294 ms** $\rightarrow$ **Nhanh hơn 7.4 lần (và nhanh hơn tới 19.5 lần với văn bản ngắn)**, hoàn toàn cục bộ và tất định.

## 5. Quyết định & Khuyến nghị Kỹ thuật cho TICK-02
1. Xóa sạch định nghĩa hàm `stage1_fast_batch_rerank` và phân nhánh `if len(docs) > 60`.
2. Thiết lập trần an toàn (Safety Cap) $N=60$ candidates trong `_stage_rerank_and_score`: `docs = [_get_hit_entity(hit).get("text", "") for hit in ctx.raw_hits[:60]]` để giữ ngân sách latency rerank $\le 1.3\text{s}$.
3. Bổ sung test case kiểm thử khâu rerank khi candidate set $> 60$ chunks.

## 6. Tiêu chí Nghiệm thu Đạt được
- [x] Xác định đầy đủ 100% các vị trí phụ thuộc và mock trong `services/rag-service/tests/`.
- [x] Bảng số liệu đo lường thực tế (Latency trung bình, P95, VRAM) giữa phương án cũ và phương án mới trên GB10.
- [x] Khuyến nghị cấu hình an toàn cho `top_k`, `batch_size`, và `max_candidates` trên GB10.
- [x] Đã unblock [TICK-02](../tickets/TICK-02-refactor-search-pipeline-bge-reranker.md).

## 7. Hiệu chỉnh sau phản biện TICK-02

- Hệ số **7,4×–19,5×** ở mục 4 được rút. ~9.550 ms là một lần timeout của gateway, không phải latency của một lượt rerank thành công.
- Cụm **“An toàn 100%”** ở mục 3 không còn là kết luận. Repo không có script đo của bảng latency, nên các số ở mục 4 chưa tái lập được từ cây mã này.
- Trần 60 là mặc định tạm trên `Settings` (`RERANK_MAX_CANDIDATES`). DEC-05 chỉ đóng sau bảng MRR theo số hiệu ở các trần 30, 60 và 100.
