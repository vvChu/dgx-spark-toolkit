# Phản biện độc lập — Bản đồ Wayfinder `MAP-SPARK-SYSTEM-ONE-20260929`

**Người phản biện:** Grok 4.7, vai trò kỹ sư trưởng hệ thống và peer reviewer đối kháng  
**Ngày:** 2026-09-29  
**Hồ sơ:** `.md/wayfinder/system-one-decision-architecture/` (map, TICK-01, TICK-02, TICK-03)  
**Mã đã đối soát:** `services/rag-service/retrieval/search_pipeline.py`, `retrieval/reranker.py`, `retrieval/query_classifier.py`, `retrieval/query_rewriter.py`, `repositories/milvus_repo.py`, `services/hitl_service.py`, `benchmarks/legal_qa_evaluator.py`, `**Phán quyết: CONDITIONAL ACCEPT.** Toàn văn nằm ở `.md/peer_exchange/grok_review_wayfinder_map.md`.

Xóa `stage1_fast_batch_rerank` là việc nên làm. Hàm đó gửi 30 khúc luật (mỗi khúc 250 ký tự) ra `claude-haiku-4` qua proxy cloud, rồi thứ tự JSON bị `bge-reranker-v2-m3` sắp lại. Trần 60 ứng viên chỉ là nút thắt độ trễ tạm thời. Cổng trích dẫn dùng chính reranker đó, và Phase 3 trên bản đồ này, không được thi công theo đặc tả hiện tại.

| Tiêu chí | Điểm |
| :--- | :---: |
| Architectural Soundness | 6 |
| Hardware & Performance Realism | 6 |
| KISS & Simplicity | 5 |
| Legal Domain Robustness | 4 |

Ba kết luận đối kháng chính:

- **`N=60` chưa phải quyết định chất lượng.** Với `limit=10`, Milvus đã xin 100 hit sau RRF. Đường Haiku thành công hôm nay chỉ đưa khoảng 30 đoạn vào cross-encoder, nên trần 60 rộng hơn đường đó. Đường timeout (~9,55 s) lại trả cả tập và cross-encoder chấm tới 100 đoạn. Tỷ số 7,4×–19,5× chia thời gian timeout cho một microbenchmark ấm, lúc GPU rảnh. `qwen36b` đang resident trên cùng GB10. Repo không có script đo. VRAM gần như phẳng từ 60 lên 100 đoạn, nên OOM không phải lý do cắt đuôi. `raw_hits[:60]` còn cắt mất hop 2 của đường agentic và không khử trùng theo `chunk_id`.

- **Điểm reranker không phải entailment.** Bản `sentence-transformers` đang cài áp `Sigmoid` vì `num_labels = 1`. Ngưỡng trên điểm đó gỡ nhầm câu kiểu “thực hiện theo quy định tại Điều 12”, và giữ nhầm câu chép đúng số điều nhưng sai nghĩa vụ. Cổng đúng việc bắt đầu bằng đối chiếu số hiệu, Điều, khoản với `doc_number` và `hierarchy_path`. Câu dẫn chiếu thuần thì giữ. Phần mệnh đề còn lại mới tới một encoder NLI. Hiệu chuẩn Platt trên điểm relevance không tạo ra nhãn mâu thuẫn.

- **FOG-02 sửa được bằng regex đã có.** `query_classifier.py` trả về ngay khi thấy một từ “Điều”, nên câu so sánh hai nghị định bị gán EXACT. Qwen 35B không vào được ngân sách 20 ms và trái quyết định cấm LLM sinh từ cho phân loại đóng. FOG-02 làm trước FOG-01. Gán nhãn lawyer chỉ bắt đầu sau khi cổng trích dẫn là NLI cộng tầng định danh. BIM QC và Maskara chưa có package trong cây. Redis DB 4 đang là hàng `HITLService` cho câu RAG. Không đẩy secret thô vào `hitl:review_queue`.

TICK-02 được merge khi trần nằm trong Settings, cắt sau khử trùng theo `chunk_id`, chừa quota cho hop 2, có khóa quanh `predict`, có test trên 61 hit và hop 2, và MRR ở trần 30, 60, 100 được đo trước khi đóng cứng DEC-05.
dưới 50 ms đã bị bác đúng hướng.** `BAAI/bge-reranker-v2-m3` là XLM-RoBERTa phân loại chuỗi, `num_hidden_layers = 24`, `max_position_embeddings = 8194`, `torch_dtype = float32` trong `config.json` của snapshot đang cache. Cross-encoder tính tương tác query–đoạn trên toàn bộ các tầng đó. Bảng TICK-01 (khoảng 0,68 s cho 30 đoạn dài, 1,29 s cho 60, 2,16 s cho 100, VRAM đỉnh gần như phẳng) có hình dạng đúng với `predict(..., batch_size=32)` trong `reranker.py`: thêm đoạn là thêm batch, đỉnh VRAM là một batch. Việc bản đồ tự bác giả thuyết 50 ms là phần nghiêm túc nhất của hồ sơ.

---

## 2. Phase 1 và TICK-01

### 2.1. Trần 60 ứng viên có bao phủ được phần recall sau RRF không

Câu trả lời trung thực: chưa có đo, và thiết kế hiện tại làm cho câu hỏi này quan trọng hơn bản đồ thừa nhận.

`_stage_hybrid_search` xin `min(limit * 10, 100)` hit. API mặc định `limit=10` nên Milvus được yêu cầu 100 hit, đã fusion bằng `RRFRanker()` (`milvus_repo.py` dòng 46–52). Nhánh `len(docs) > 60` vì vậy là đường thường gặp với limit mặc định, không phải đường “exceptionally large” như comment ở dòng 601.

Trên đường LLM trả index hợp lệ, prompt chỉ nhìn `docs[:30]`. Cross-encoder phía sau chỉ thấy tập đã bị thu hẹp quanh nhóm đầu đó. `raw_hits[:60]` rồi chấm điểm bằng cross-encoder **rộng hơn đường thành công hiện tại**. So với đường hôm nay khi Haiku làm việc đúng, trần 60 là một bước tăng recall, không phải một bước cắt.

So với đường thất bại thì ngược lại. `complete()` dùng `retries` như số lần thử trong `range(max_retries)`, không phải số lần thử thêm (`ai_gateway_client.py` dòng 180). `retries=1` với chain hai mô hình, timeout 4 s và `sleep(1)` sau lỗi, ra khoảng 9 s. Con số 9.550 ms trong TICK-01 khớp đường cả hai mô hình đều hết giờ. Khi đó `except` ở dòng 220–224 trả **cả** `docs`, và cross-encoder chấm tới 100 đoạn. Đường hỏng hôm nay chậm hơn và nhìn nhiều ứng viên hơn. Trần 60 nhanh hơn đường hỏng, và bỏ 40 hit cuối của RRF mà chưa ai đo độ mất.

RRF đã sắp xếp. Cắt `[:60]` trên đường hybrid thường là cắt đuôi fusion, đúng chỗ để cắt nếu buộc phải cắt. Không có recall@60, recall@100 hay MRR trên bộ hỏi đáp pháp lý trong TICK-01. `benchmarks/legal_qa_evaluator.py` đã có MRR theo số hiệu văn bản kỳ vọng. Đó là dụng cụ sẵn có. DEC-05 đóng cứng trần 60 trước khi chạy dụng cụ đó.

Hai hiệu ứng làm 60 slot thực tế hẹp hơn 60 văn bản:

- Đường thường không khử trùng trước khi cắt. `chunk_id` có trong `output_fields` của hybrid search và không được pipeline dùng. Parent và child của cùng một điều, hoặc hai hit trùng `text`, cùng chiếm slot. `hit_map` (dòng 613–617) giữ hit đầu tiên theo nguyên văn `text`.
- Đường agentic lấy `min(limit * 5, 40)` hit mỗi sub-query, tối đa 3 sub-query, rồi nối hop 2 vào cuối (`_agentic_reflect_and_hop2`, dòng 574–580). `raw_hits[:60]` ưu tiên hop 1. Đủ 60 hit unique ở hop 1 thì hop 2 bị bỏ sạch. Hop 2 là lý do tồn tại của nhánh này.

Với truy vấn EXACT (đúng số hiệu, đúng Điều), sparse đáng lẽ đưa điều đó vào top đầu; 60 là dư. Với truy vấn ngữ nghĩa trên QCVN dài, điều đúng có thể nằm ở hạng 70–100 của RRF vì parent chunk dài và từ vựng lệch. Mất mát đó chưa được đo. Trần 60 chấp nhận được như mặc định tạm thời cho đường semantic, sau khi khử trùng theo `chunk_id` và chừa ngân sách cho hop 2. Nó chưa đủ tư cách quyết định chất lượng đã chốt.

### 2.2. Ngân sách khoảng 1,29 s có chấp nhận được không

Có, như một thành phần của câu trả lời pháp lý nhiều bước. Không, như một khoản thuế phẳng trên mọi truy vấn.

1,29 s là trung bình warm cho 60 đoạn khoảng 1.300 ký tự, batch 32, fp32, một tiến trình không bị vLLM tranh SM. P95 công bố của hàng `N=60` bằng đúng max (1.299,81 ms), biên độ min–max chỉ 11 ms. Cột đó mô tả một mẫu ấm rất chặt, không mô tả đuôi khi `qwen36b` đang decode. Lúc rà soát, container `qwen36b` đã up 14 giờ và một mẫu `nvidia-smi` báo GPU util 0%. TICK-01 không ghi vLLM có đang nằm trong bộ nhớ hay không. Trên GB10 unified memory, cross-encoder và vLLM dùng chung SM. Con số 1,29 s là cận dưới của thời gian rerank khi GPU rảnh.

Người dùng hỏi đáp kỹ thuật chờ phần sinh câu trả lời lâu hơn 1 s. Cộng 1,3 s rerank vào đường semantic là chấp nhận được nếu cả retrieval đứng dưới vài giây. Nó là khoản xấu trên đường EXACT: câu “Điều 5 QCVN 06:2022” không cần 60 lần cross-attention. Bộ phân loại ý định đã có kết quả trước khi retrieve. Trần nên phụ thuộc ý định: EXACT hẹp (khoảng 15–20), semantic giữ 60 tạm thời, agentic tính ngân sách theo hop.

Phần còn lại của hot path vẫn là System Two. `rewrite_query` gọi cùng `claude-haiku-4` với timeout 2 s trên mọi câu chưa nằm trong cache bộ nhớ (`query_rewriter.py` dòng 44–56). Đường COMPLEX còn HyDE, plan sub-query, evaluate, và tóm tắt timeline. Câu ở Destination “khử bỏ hoàn toàn System Two trên hot-path retrieval” rộng hơn diff của TICK-02. Sau khi xóa stage1, retrieval vẫn còn các vòng sinh từ đó.

Tỷ số 7,4×–19,5× là phép chia đúng trên hai số đã chọn: 9.550 / 1.294 ≈ 7,4 và 9.550 / 495 ≈ 19,3. Mẫu số là microbenchmark ấm. Tử số là một lần gateway timeout, chưa cộng nốt cross-encoder chạy trên full set sau `except`. Đường Haiku thành công (thường 1–2 s) cộng rerank 30 đoạn (0,68 s trong chính bảng của họ) nằm gần 1,29 s hơn là gần 9,5 s. Giữ phát biểu tốc độ ở dạng: xóa một vòng mạng có thể treo ~9 s, phần rerank local ấm nằm trong khoảng 0,5–1,3 s tùy độ dài đoạn. Bỏ hệ số 7,4×–19,5× khỏi DEC-05.

`21,5 ms/chunk` cũng chỉ là trung bình của hàng dài: 1.294 / 60 ≈ 21,6 ms. Hàng ngắn là 495 / 60 ≈ 8,2 ms. Batch thứ hai của hàng dài thêm khoảng 20,5 ms/đoạn. Đó là hàm của độ dài chuỗi và số batch, không phải hằng số của GB10. TICK-01 ghi cả hai độ dài. DEC-05 trên map nhập chúng thành một hằng số.

VRAM không biện minh cho trần 60. Đỉnh 2.699,6 MB ở `N=60` và 2.699,8 MB ở `N=100` lệch nhau 0,2 MB. Mức tăng 31 MB từ `N=30` lên `N=60` khớp việc đỉnh bộ nhớ là một batch 32. `N=100` không đưa máy này tới OOM. Nút thắt là latency. Trước khi đổi nút thắt thành mất 40 hit, đáng đo cùng bảng ở bf16 hoặc fp16: config đang là float32, XLM-R large fp32 khoảng 2,2 GB trọng số. Blackwell xử lý bf16 tốt. Nếu `N=100` ở bf16 vẫn dưới ngân sách 1,3 s, trần 60 là nút sai.

Cửa sổ 8192 token là thật với tokenizer đang cache (`model_max_length = 8192`; `min(8192, 8194)` trong constructor CrossEncoder). Ràng buộc đang siết là `doc[:1500]` ở `reranker.py` dòng 42. Một chuỗi tiếng Việt lặp, 1.500 ký tự, ra 359 token với chính tokenizer đó. Parent chunk được phép dài tới `CHUNK_MAX_CHARS = 14500` (`chunkers/base.py`) và Milvus lưu `text[:14000]`. Cross-encoder chấm prefix 1.500 ký tự rồi trả nguyên văn đầy đủ cho LLM. Khoản nằm sau ký tự 1.500 không tham gia xếp hạng. Child chunk chỉ ngắn khi bộ tách câu chịu cắt (`min_child_length = 300`, không có trần dưới `MAX_CHUNK_CHARS`). Một khoản dài không có dấu ngắt câu thành một child khổng lồ và bị chấm nửa đầu. TICK-01 gọi cơ chế cắt này là “an toàn 100%”. Nó an toàn cho bộ nhớ. Nó mù với nửa sau điều luật.

Tiêu chí nghiệm thu của TICK-01 ghi đã có bảng latency/P95/VRAM cho cả phương án cũ và phương án mới. Bảng published chỉ có phương án mới. Phương án cũ là một số ~9.550 ms, không có P95, không có VRAM, không có số lần chạy. Trong repo không có script, log, seed, hay `nvidia-smi` của phiên đo. Theo `docs/PITFALLS.md` mục 9, số đo LLM dễ dính cache; mục 14 nói lần predict lạnh của reranker trên GB10 khoảng 34 s và thuộc warmup, không thuộc SLA từng câu. Bảng TICK-01 dùng được như số ấm nội bộ. Nó không đủ để một SLO.

### 2.3. “Không có test nào đụng stage1 nên refactor an toàn 100%”

Vế đầu đúng. `grep` trên `services/rag-service/tests/` không thấy `stage1_fast_batch_rerank`. Ba test rerank trong `tests/test_search_pipeline.py` mỗi test một hit và mock `get_reranker().rerank`. Xóa hàm sẽ không làm đỏ suite hiện tại.

Vế sau đảo nghĩa của khoảng trống đó. Nhánh `len(docs) > 60` chưa từng được thực thi trong test. Suite xanh chứng minh CI không khóa hành vi này. Một test “nhiều hơn 60 hit thì chỉ đưa 60 chuỗi vào `rerank`” là cần, và chưa đủ. Ma trận tối thiểu nằm ở mục 6.

---

## 3. Bẫy trong diff TICK-02

Diff đề xuất (cắt `ctx.raw_hits[:60]`, lấy `text`, gọi `rerank`) xử lý đúng ca danh sách hybrid đã sắp theo RRF, text duy nhất, ngắn hơn 60. Các ca sau nằm ngoài snippet.

1. **Hop 2 bị cắt bởi thứ tự nối danh sách.** Xem mục 2.1. Cắt sau khi đã `all_hits.append` hop 2 thì hop 2 đứng ở đuôi và rơi trước. Cắt theo từng hop: giữ quota hop 2 (ví dụ 20) rồi mới lấp phần còn lại bằng hop 1, sau khử trùng.

2. **Khóa `hit_map` bằng nguyên văn `text`.** Hai chunk cùng text, khác `doc_number` / `revision` / `page`, gộp thành một metadata. `rerank` trả về đúng chuỗi đã đưa vào (`zip(docs, scores)` trên bản gốc, không phải bản `[:1500]`), nên lookup khớp khi chuỗi không bị sửa. Khóa này gãy ngay nếu ai “tiện tay” đưa bản đã cắt 1.500 ký tự vào `rerank` rồi tìm lại bằng text đầy đủ. Khóa bền là `chunk_id`, kèm danh sách song song. Milvus đã trả field đó.

3. **Slot bị ăn bởi trùng lặp.** Dedup agentic dùng `text[:200]`. Dedup đường thường không có. Trần 60 phải đếm chunk duy nhất theo `chunk_id`, nếu thiếu thì theo hash của text đầy đủ. Nếu không, 60 là trần của bản sao.

4. **Danh sách rỗng đã được chặn, danh sách text rỗng thì chưa.** `if not ctx.raw_hits: return` xử lý `None` và `[]`. Hit có `text` rỗng vẫn đi vào `rerank`. `rerank_sync` chỉ trả `[]` khi `docs` rỗng. Nhiều hit rỗng gộp về cùng khóa `""`. Không làm vỡ pipeline. Test nên khóa hành vi này để lần sửa sau không đổi ngầm.

5. **`get_reranker()` là singleton không có khóa quanh `predict`.** `_load_lock` chỉ bọc load. FastAPI gọi `asyncio.to_thread(self.rerank_sync)` song song trên cùng một `CrossEncoder`. Hai `predict` CUDA xen kẽ là lỗi sẵn có. TICK-02 kéo mỗi request từ “đôi khi 30 đoạn, sau một vòng mạng” thành “luôn tới 60 đoạn”, cửa sổ chồng lấn dài hơn. Một `threading.Lock` quanh `predict` là phần của diff, không phải việc để sau.

6. **Điểm trả về đã qua sigmoid, rồi bị trộn với điểm Milvus.** Config reranker có `num_labels = 1` (xác nhận bằng `AutoConfig` trên snapshot), không có `sentence_transformers.activation_fn`. `CrossEncoder.get_default_activation_fn` trả `nn.Sigmoid()` khi `num_labels == 1`, và `predict` áp nó lên logit (CrossEncoder.py dòng 491–493 và 715). `rerank()` vì vậy trả giá trị trong (0, 1). Sigmoid đơn điệu, thứ tự xếp hạng giữ nguyên. Công thức ở dòng 631 là `0.8 * sigmoid + 0.2 * điểm Milvus + boost bảng + boost hiệu lực`. Điểm Milvus của RRF và điểm cosine ở đường fallback dense không cùng thang với nhau. Ngưỡng grounding 0,65 ở dòng 315 đứng trên hỗn hợp này. TICK-02 không tạo ra sự lệch thang. TICK-02 cũng không được phép lấy hỗn hợp đó làm `τ_citation`.

7. **Hết GPU thì cả request chết.** `rerank_sync` không có fallback về thứ tự RRF. Một lỗi CUDA làm hỏng câu trả lời thay vì trả hit Milvus. Bọc `rerank` trong try/except, log, và giữ thứ tự `candidate_hits` khi mô hình không chấm được. Đây là lưới an toàn của việc biến cross-encoder thành tầng lọc duy nhất.

8. **Không có histogram riêng cho ngân sách 1,3 s.** `rag_search_latency_seconds` có bucket bắt đầu từ 1 s cho cả request. Tracer có step `rerank`. Một histogram `rag_rerank_candidates` và `rag_rerank_latency_seconds` là cách duy nhất để biết trần 60 còn đúng sau khi `qwen36b` bận. Không có metric thì DEC-05 không kiểm soát được.

9. **Snippet trong ticket dễ dán đè chưa xóa dòng cũ.** Đoạn mới tự xây `candidate_docs` từ hit, trong khi hàm hiện vẫn xây `docs` rồi rẽ nhánh. Tiêu chí nghiệm thu phải là assertion trên đối số của `rerank` và trên việc `complete_json` không được gọi, không phải là “đã sửa file”.

10. **Hằng số nằm trong code.** `60` cần thành `RERANK_MAX_CANDIDATES` trên `Settings`, mặc định 60, đọc một chỗ. Ma thuật nằm trong thân hàm sẽ bị agentic và ad-hoc RAG nhân bản.

Ca `docs` rỗng sau khi đã có hit không phải bẫy chính. Bẫy chính là hop 2, khóa theo text, và sự chồng CUDA.

---

## 4. Citation Noul Gate (TICK-03)

### 4.1. Reranker đa ngữ không phải bộ entailment

`bge-reranker-v2-m3` được huấn luyện để xếp độ liên quan truy vấn–đoạn (dữ liệu retrieval đa ngữ). Đầu ra một nhãn, điểm sau sigmoid, dùng để sắp. Bài toán trích dẫn là: câu khẳng định có được đoạn nguồn chống đỡ, có bị đoạn nguồn bác, hay chỉ cùng chủ đề. Đó là ba nhãn entailment / contradiction / neutral.

Điểm liên quan cao khi cụm từ của câu xuất hiện trong đoạn. Hai lỗi pháp lý điển hình nằm đúng ở chỗ hàm đó mù:

- **Giữ nhầm (nguy hiểm hơn).** Câu bịa nghĩa vụ, nhưng chép đúng “Điều 12” và vài danh từ của đúng điều. Relevance cao. Cổng để lọt footnote sai. Ảo giác số hiệu lệch một điều trong cùng QCVN là hard negative: chồng từ vựng rất cao, giá trị pháp lý bằng không.
- **Gỡ nhầm.** Câu viện dẫn gián tiếp, dạng “thực hiện theo quy định tại Điều 12”, không nhắc lại chỉ tiêu kỹ thuật. Đoạn nguồn là khoản chỉ tiêu. Ít token chung. Điểm relevance tụt. Cổng gỡ một trích dẫn hợp lệ. Văn bản xây dựng Việt Nam đầy dẫn chiếu kiểu này. Một ngưỡng cắt trên điểm liên quan sẽ tạo false negative hàng loạt trên đúng văn phong đó.

Hiệu chuẩn Platt hoặc temperature scaling không sửa được sự lệch tác vụ. Hiệu chuẩn làm cho một điểm mono trở thành tần suất. Nó không tạo ra nhãn “mâu thuẫn”. TICK-03 gọi giá trị này là “logit tương quan ngữ nghĩa”. Với bản sentence-transformers đang cài, `predict` đã bọc sigmoid. Ngưỡng 0,75 trong bài nghiên cứu nội bộ chỉ có nghĩa trên thang (0, 1) đó, và nghĩa đó là “khá liên quan”, không phải “được đoạn này entail với xác suất 0,75”.

`legal_qa_evaluator.py` dòng 111–116 đã ghi heuristic chồng token 40% và chú thích rằng production cần một mô hình NLI riêng. `evaluation/evaluator.py` thì hỏi LLM chấm faithfulness, đúng kiểu System Two mà DEC-01 cấm trên đường nóng. TICK-03 bỏ qua cả hai: bỏ baseline lexical sẵn có, và thay judge LLM bằng một mô hình retrieval. Hướng bỏ judge LLM là đúng. Mô hình thay thế thì chọn nhầm họ.

### 4.2. Cổng đáng xây

Ba tầng, đúng thứ tự DEC-01 đã viết. Tầng mã chạy trước. Mô hình chỉ thấy phần tầng mã không kết luận được.

**Tầng 0, định danh.** Tách số hiệu, Điều, khoản, điểm bằng regex có sẵn cùng họ với `query_classifier.py` (QCVN/TCVN, `NN/YYYY/XX-YYY`, `Điều\s+\d+`). Đối chiếu với `doc_number` và `hierarchy_path` của chunk gắn footnote. Lệch định danh thì gỡ trích dẫn, không cần điểm nổi. Câu chỉ là con trỏ (“thực hiện theo quy định tại Điều 12…”) mà định danh khớp chunk thì **giữ**, và không đưa vào NLI. Đây là phòng thủ chính cho viện dẫn gián tiếp. False negative của cross-encoder trên câu kiểu này được xử lý bằng cách không hỏi cross-encoder.

**Tầng 1, phần mệnh đề.** Phần còn lại của câu, sau khi đã tách cụm viện dẫn, mới là claim. Heuristic chồng token hiện có là baseline để mô hình phải thắng trên cùng tập hard negative. Không dùng nó làm lưỡi xóa trong sản phẩm.

**Tầng 2, NLI.** Một encoder entailment đã có tiếng Việt trong tập nhãn, cỡ base (họ mDeBERTa XNLI, khoảng vài trăm triệu tham số, fp16 dưới 1 GB). Nằm trong ràng buộc VRAM của bản đồ (cấm thêm decoder 8B/14B, không cấm một encoder base). Ba nhãn. Mâu thuẫn đã hiệu chuẩn mới được gỡ. Vùng giữa đánh dấu `unverified` và vẫn hiện trích dẫn. Gỡ footnote của kỹ sư xây dựng là mất dấu để kiểm; giữ một dấu `unverified` thì không mất dấu. `bge-reranker-v2-m3` ở lại đúng việc xếp hạng truy hồi.

Hard negative bắt buộc khi gán nhãn: cùng văn bản, Điều kề bên, cùng định nghĩa (“công trình”, “chiều cao”, “PCCC”), và cặp mâu thuẫn số liệu trong bảng. Cặp ngẫu nhiên khác chủ đề làm AUROC đẹp và ngưỡng vô dụng.

### 4.3. Tiêu chí dưới 30 ms cho 5 trích dẫn lặp lại giả thuyết TICK-01 vừa bác

TICK-01 đo khoảng 679 ms cho một batch 30 cặp dài, tức hơn 20 ms/cặp trước khi kể overhead. Năm cặp dài không suy ra 30 ms. Chúng có thể là một batch nhỏ, vẫn chịu giá khởi động kernel và vẫn xếp hàng sau vLLM. Tiêu chí nghiệm thu “< 30 ms cho 5 trích dẫn” phải bị xóa khỏi TICK-03 cho đến khi có cùng kiểu bảng như TICK-01, đo lúc `qwen36b` đang resident. Cổng trích dẫn chạy sau khi sinh câu, nên latency cộng thêm vào thời gian người dùng thấy, không núp trong 1,29 s của retrieval.

Phụ thuộc “TICK-03 blocked by TICK-02” là phụ thuộc lịch, không phải phụ thuộc kỹ thuật. Thiết kế lại cổng theo mục 4.2 có thể viết song song. Không mở khóa TICK-03 bằng cách giữ nguyên đặc tả sau khi TICK-02 merge.

### 4.4. FOG-01: bao nhiêu mẫu

Câu hỏi trong map trộn ba thứ: độ chính xác, khoảng tin cậy 95%, và calibration. Trả lời tách ra.

- 50–100 cặp, như TICK-03 đề xuất, là pilot đọc lỗi. Đủ để thấy viện dẫn gián tiếp và Điều-kề-bên có làm vỡ ngưỡng hay không. Không đủ để khóa một ngưỡng xóa footnote.
- Ước lượng một tỷ lệ với sai số ±5 điểm phần trăm, độ tin cậy 95%, ở tỷ lệ gần 0,5, cần khoảng 385 mẫu cho riêng tỷ lệ đó (`1,96² × 0,25 / 0,05²`). Ở tỷ lệ lỗi gần 0,1 và cùng sai số, khoảng 140. Đó là cỡ mẫu của một con số, chưa phải của một đường calibration.
- Để được phép gỡ trích dẫn: khoảng 200 cặp entailment, 200 cặp không được chống đỡ hoặc mâu thuẫn, 200 hard negative cùng văn bản, cộng một lớp con trỏ thuần để xác nhận tầng 0 bỏ qua NLI. Cỡ 600 cặp do người biết chuyên môn gán, chia tập khóa ngưỡng và tập giữ lại. Temperature scaling mà báo cáo dám gọi là đáng tin cần tập giữ lại riêng, cùng độ lớn, không dùng lại tập đã chọn ngưỡng.
- Gán nhãn trên điểm `bge-reranker` trước khi đổi đầu NLI thì 600 cặp đó bị tiêu vào một điểm mono. FOG-01 đứng sau quyết định mô hình ở mục 4.2, không đứng trước.

---

## 5. FOG-02 đến FOG-04, và Phase 3

### 5.1. FOG-02 đã có mã. Việc còn lại là sửa thứ tự rule

`retrieval/query_classifier.py` đã phân loại `EXACT` / `COMPLEX` / `SEMANTIC` bằng regex, không gọi LLM, độ trễ ở mức microsecond chứ không phải ngân sách 20 ms. Destination Phase 2 viết như thể bộ phân loại này chưa tồn tại.

Hai lỗi đang nằm trong file:

- Vòng EXACT `return` ngay lần khớp đầu. Mẫu `Điều|Khoản|Điểm` đứng trước mọi mẫu COMPLEX. Câu “so sánh Điều 15 Nghị định 87/2023/NĐ-CP và Điều 16 Nghị định 88/2023/NĐ-CP” khớp `article_reference` và ra EXACT với confidence 0,90. Nhánh so sánh, sửa đổi, và nhiều số hiệu không bao giờ chạy. Confidence 0,90 là hằng số, không phải xác suất đã hiệu chuẩn.
- Mẫu `trước|sau|từ năm` rất rộng. “Biện pháp an toàn trước khi đào móng” thành COMPLEX, bật HyDE và agentic, tức là tự mở thêm System Two.

`get_search_weights` chỉ được gọi trong `tests/test_optimizations.py`. `hybrid_search` luôn `RRFRanker()` trần. Docstring nói weight theo ý định sẽ chỉnh RRF. Trên đường chạy thì không.

Qwen 35B với `enable_thinking: False` bị loại. `extract_json` đã đặt `enable_thinking: False` cho mọi lần rút JSON. Một decoder 35B đang chia GPU với chính job sinh câu không có đường tới 20 ms, và dùng nó để phân loại ba nhãn thì trái DEC-01. Timeout 2 s của `rewrite_query` là bằng chứng vận hành rằng cùng họ mô hình không sống trong ngân sách mili-giây.

PhoBERT là thêm một bộ trọng số, chưa có đầu phân loại ý định, để sửa một lỗi thứ tự `if`. Đo confusion trên log truy vấn thật sau khi đảo ưu tiên: mẫu nhiều số hiệu và mẫu “so sánh / mâu thuẫn” xét trước mẫu một Điều đơn. Nếu sau lần sửa đó tỷ lệ lệch vẫn cao trên câu diễn giải không có từ khóa, lúc đó mới xét encoder nhỏ. Không mở một bake-off mô hình trong FOG-02.

**Thứ tự với FOG-01:** làm FOG-02 trước, trong phạm vi sửa và đo regex. Nó đổi tập hit trước cả trần 60, nên nó ảnh hưởng Phase 1. FOG-01 đứng sau khi cổng trích dẫn đã là NLI cộng tầng định danh. Gán nhãn lawyer cho reranker trong lúc bộ phân loại còn nuốt câu so sánh là tiêu tiền đo vào hai chỗ cùng lúc.

### 5.2. Phase 3 đang vượt phạm vi của bản đồ này

Nguyên tắc thì đúng: taxonomy đóng thì dùng mã hoặc scorer, không hỏi LLM viết nhãn tự do. Cách bản đồ đưa nguyên tắc ấy vào Destination thì vượt quá những gì repo này chứa.

`packages/ccba-bim-qc` và `packages/ccba-maskara` không có trong cây. Map vẫn liệt kê chúng như hệ thống liên quan. Một scorer System One cần tập nhãn đã đóng và một baseline LLM đang thất bại trên chính tập đó. FOG-03 hỏi taxonomy có bao nhiêu cấp và làm sao biến thuộc tính IFC thành vector. Câu hỏi thứ hai đi trước câu hỏi thứ nhất, và đi trước tầng mã của chính DEC-01. Kiểm tra hồ sơ IFC/Revit kiểu Solibri là rule trên thuộc tính có cấu trúc: thiếu property, sai đơn vị, lệch phân loại. Phần đó là Python, không phải embedding. Scorer chỉ có việc với phần mô tả mơ hồ còn sót sau khi taxonomy và rule đã đứng. Trả lời FOG-03 bằng câu đó, rồi đưa nó sang một bản đồ khác khi package tồn tại.

FOG-04 đụng một hàng đợi đã có chủ. `HITLService` (`services/hitl_service.py`) dùng Redis DB 4, khóa `hitl:review_queue`, schema là query RAG, top 3 snippet, lý do `random_sample | low_confidence | manual`, điểm người chấm 1–5. Trần 500 phần tử, đầy thì bỏ qua và trả false. `submit_review` đẩy sang list khác và không gỡ phần tử khỏi hàng chờ. Parser URL tự viết lại path `/4`. `docs/PITFALLS.md` mục 3 dành DB 4 cho đúng dịch vụ này.

Đặt secret Maskara vào hàng đó có bốn hệ quả:

- Schema không có span, loại bí mật, hay id tài liệu. Dashboard review RAG sẽ đọc thấy nguyên liệu bí mật.
- Redis AOF của DB 4 lưu durable phần tử hàng đợi. Secret nằm trên đĩa cạnh log review pháp lý.
- Trần 500 đang phục vụ sample RAG. Đầy thì secret bị drop im lặng. Với dữ liệu nhạy cảm, drop là fail-open.
- Khoảng 0,60–0,95 rộng 35 điểm. Bản đồ không nói miền dưới 0,60 làm gì. Nếu miền đó có nghĩa là “cho qua”, key dạng cao mà điểm mô hình thấp sẽ lọt. API key, PEM, chuỗi kết nối thuộc tầng regex, redact ngay, không xếp hàng. HITL chỉ dành cho PII mơ hồ. Trên kho văn bản pháp luật, tên người ký và số hiệu công văn là nội dung phải giữ. Trộn “redact log” với “redact điều luật” là một chính sách sai miền.

Nếu Maskara sau này cần người xem: khóa Redis riêng, payload đã redact cộng hash, không tái sử dụng `hitl:review_queue`, và dưới ngưỡng của pattern độ chính xác cao thì vẫn redact.

Phase 3 vì vậy không phải hướng sai của DEC-01. Nó là phần làm bản đồ này hết tinh gọn. Điểm đích còn lại là Phase 1 có điều kiện, và Phase 2 sau khi viết lại.

---

## 6. Điều kiện để gỡ chữ “conditional”

TICK-02 được merge khi các mục sau vào cùng diff hoặc được ghi rõ là việc chặn ngay sau đó.

1. Xóa `stage1_fast_batch_rerank` và mọi lời gọi `complete_json` trong rerank.
2. `RERANK_MAX_CANDIDATES` trên Settings, mặc định 60. Cắt sau khử trùng theo `chunk_id`. Trên đường agentic, chừa quota cho hop 2. EXACT dùng trần hẹp hơn; số cụ thể được ghi trong Settings, không nhân thêm một mô hình.
3. `hit_map` khóa bằng `chunk_id`.
4. Khóa thread quanh `CrossEncoder.predict`. Lỗi predict thì giữ thứ tự hit đã cắt và log.
5. Histogram latency và số ứng viên của riêng bước rerank.
6. Test: 0 hit; 1 hit; 61 hit thì đối số `rerank` dài 60 và hit thứ 61 vắng; hai hit trùng text khác `doc_number` giữ đúng metadata của chunk được chọn; đường agentic với hop 1 dài và hop 2 ngắn vẫn còn chunk của hop 2; `complete_json` không được await. Mock như các test hiện có, không cần GPU.
7. Sửa câu Destination: Phase 1 xóa LLM khỏi **bước rerank**, không phải khỏi toàn bộ retrieval. Gỡ hệ số 7,4×–19,5× và chữ “an toàn 100%” khỏi map. Gắn script đo của TICK-01 vào repo hoặc ghi trong ticket là số chưa tái lập được.
8. Chạy `LegalRAGEvaluator` (MRR theo số hiệu) ở trần 30, 60 và 100 trên tập QA pháp lý đang có, lúc GPU ở trạng thái giống production. DEC-05 chỉ đóng sau bảng đó. Trong thời gian chờ, 60 là mặc định tạm.

TICK-03 chỉ được mở lại khi đặc tả đổi thành mục 4.2, tiêu chí 30 ms bị xóa, và tập gán nhãn được định nghĩa bằng hard negative. FOG-02 đóng bằng diff `query_classifier.py` cộng một bảng đếm trên câu thật, không bằng PhoBERT và không bằng Qwen. FOG-03 và FOG-04 rời Destination; DB 4 giữ nguyên hợp đồng của `HITLService`.

---

## 7. Bảng điểm

Thang 1–10 cho toàn bản đồ như một văn bản điều hành, không chấm riêng ý “hãy xóa stage1”.

| Tiêu chí | Điểm | Vì sao mức này |
| :--- | :---: | :--- |
| Architectural Soundness | **6** | DEC-01 đúng bệnh của stage1: hoán vị LLM chết ở bước sau, và đoạn luật đang ra cloud proxy. Phase 2 dùng điểm relevance làm cổng entailment, trái chính tầng mã → scorer → CoT mà DEC-01 đã viết. Câu “hết System Two trên hot path” không đúng với `rewrite_query`, HyDE và agentic. |
| Hardware & Performance Realism | **6** | Tự bác 50 ms, khớp 24 tầng, batch 32, fp32 ~2,7 GB, VRAM phẳng khi tăng `N`. Điểm bị kéo xuống vì baseline 9,55 s là đường timeout, P95 trùng max trên mẫu ấm, không có script, không nói vLLM có resident hay không, và TICK-03 viết lại ngân sách 30 ms. Trần 60 không được biện minh bằng OOM. |
| KISS & Simplicity | **5** | Diff TICK-02 bản thân nó gọn. Bản đồ thì dựng lại một router đã có, dùng một điểm reranker cho ba loại quyết định, đưa Platt vào trước khi có đầu NLI, và mở Phase 3 trên package không nằm trong cây. |
| Legal Domain Robustness | **4** | Chưa có recall@k trên câu hỏi luật Việt Nam. Prefix 1.500 ký tự bỏ nửa sau điều dài. Parent/child nuốt trần 60. Regex EXACT nuốt câu so sánh điều khoản. Viện dẫn gián tiếp sẽ bị một ngưỡng relevance gỡ nhầm, trong khi ảo giác cùng điều được giữ. Tầng định danh (`doc_number`, `hierarchy_path`) đã nằm trên hit và chưa được dùng làm cổng. |

Điểm kiến trúc và phần cứng không thấp hơn 6 vì phần tự phản biện của TICK-01 là thật: họ đo xong thì bỏ giả thuyết đẹp. Một bản đồ giữ nguyên “60 đoạn trong 50 ms” sẽ ở mức 3. Điểm miền luật ở 4 vì công cụ sửa (regex số hiệu, `hierarchy_path`, evaluator MRR, heuristic faithfulness) đã có trong repo và bản đồ không dùng.

---

## 8. Kết luận

Giữ hướng Phase 1. Viết lại diff TICK-02 cho đủ hop 2, `chunk_id`, khóa GPU, test, và hằng số cấu hình. Coi `N=60` là tạm cho đến khi MRR trên bộ QA pháp lý so được 60 với 100. Dừng TICK-03 ở dạng “sigmoid của reranker, dưới ngưỡng thì xóa footnote”. Cổng trích dẫn bắt đầu bằng đối chiếu số hiệu và Điều với metadata của chunk; câu dẫn chiếu thuần không đi qua mô hình; phần mệnh đề còn lại mới tới một encoder NLI. Đóng FOG-02 bằng cách sửa thứ tự rule trong `query_classifier.py`. Để BIM và Maskara sang bản đồ riêng, sau khi có mã và taxonomy, và không ghi secret vào `hitl:review_queue`.

Đó là CONDITIONAL ACCEPT. Phần được thi công ngay là việc xóa stage1 dưới các điều kiện của mục 6. Phần chưa được thi công là cổng Noul trên `bge-reranker-v2-m3` và mọi scorer Phase 3.
