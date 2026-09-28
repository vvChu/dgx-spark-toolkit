---
name: ccba-vllm-manager
description: Quản trị mô hình vLLM trên DGX Spark Blackwell GB10, tối ưu hóa AOT Inductor cache, và cấu hình phân tách reasoning/tool parsers.
applies_to:
- Hạ tầng GPU
- Mô hình cục bộ
- Trích xuất dữ liệu
bundle: _software
tier: domain
command: /ccba-vllm-manager
metadata:
  version: "1.2.0"
  author: "CCBA Hub"
gpi:
  s: 3.0
  k: 2.0
  a: 3.0
  p: 1.0
triggers:
- vllm
- qwen
- reasoning parser
- inductor cache
- dgx spark
- local llm
- thinking token
---

# vLLM Manager

Kỹ năng này cung cấp cho Agents và Kỹ sư hạ tầng toàn bộ tri thức và chỉ dẫn vận hành để quản lý **vLLM model serving** trên máy trạm NVIDIA DGX Spark (128GB LPDDR5x unified memory, chip Grace Blackwell GB10).

| Model vật lý | Functional Alias | Port vLLM | Container | VRAM / RAM | Đặc tính kỹ thuật |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B-FP8 | `rag-core` / `local-coder` | 8004 | `qwen36b` | ~35GB (50G cap) | ✅ MoE + FlashInfer + Dual Parser (`qwen3` / `qwen3_coder` / auto-tool-choice) |
| Qwen3.6-35B (Instruct) | `local-instruct` | 8090 (Gateway) | Via `qwen36b` | — | ✅ Forced `enable_thinking: False`, siêu tốc độ ~0.2s |
| cyankiwi/Qwen3.5-9B-AWQ-4bit | `rag-light` | 8003 | `qwen3-9b` | ~10GB | ✅ Fast Fallback (AWQ 4-bit) |

> [!TIP]
> **Quy tắc Bất Biến Routing**: LUÔN sử dụng functional aliases (`local-instruct`, `rag-core`, `local-coder`) thay vì nhúng tên mô hình vật lý trực tiếp vào mã nguồn.

---

## 1. Tối Ưu Hóa Hạ Tầng: AOT Inductor Cache Volume Mount

Dòng mô hình hybrid attention + MoE thế hệ mới (như Qwen 3.6) sử dụng `torch.compile` / Inductor graph để tăng tốc độ inference. Mỗi lần container vLLM khởi động lại, quá trình biên dịch đồ thị AOT mất từ **35 - 45 giây**.

### Chỉ dẫn Volume Mount Bắt Buộc
BẮT BUỘC mount thư mục lưu trữ cache từ host vào container trong `docker-compose.yml`:

```yaml
# Trích đoạn docker-compose.yml dịch vụ vllm-36b
services:
  vllm-36b:
    image: vllm/vllm-openai:latest
    container_name: qwen36b
    volumes:
      - /home/vvc/.cache/vllm:/root/.cache/vllm  # Persistent AOT Inductor Cache
      - /home/vvc/.cache/huggingface:/root/.cache/huggingface
      - /home/vvc/models/Qwen3.6-35B-A3B-FP8:/models/model
    ipc: host
```

> [!IMPORTANT]
> **Quy tắc quyền sở hữu (UID & Cache Ownership)**:
> - Container vLLM chạy dưới user `root`, nên các cây thư mục con do vLLM sinh ra bên trong `/home/vvc/.cache/vllm` (`torch_compile_cache`, `flashinfer_autotune_cache`, `modelinfos`) mang quyền `root:root 755`.
> - User thường `vvc` (UID 1000) không thể dọn dẹp các tệp này nếu không có quyền `sudo`.
> - **CẤM** chạy `chmod 777` lên thư mục cache. Khi thay đổi image digest (`docker pull`), hãy di chuyển thư mục cache cũ sang backup thay vì ghi đè trực tiếp.

---

## 2. Cấu Hình Phân Tách Parser (Dual Parser & Anti-Double-Parser)

Khi sử dụng Qwen 3.6 với cả khả năng suy luận (Reasoning CoT) và gọi công cụ (Tool / Function Calling), cấu hình parser phải tuân thủ nghiêm ngặt nguyên tắc phân định vai trò:

### Cấu hình phía vLLM Container
Các tham số sống được quản trị tập trung tại `docker-compose.yml` (service `vllm-36b`) và file `.env` (`LOCAL_PRIMARY_MAX_MODEL_LEN=98304`, `LOCAL_PRIMARY_GPU_UTIL=0.60`).

Bộ cờ bắt buộc cho vLLM 0.26+:
```bash
--reasoning-parser qwen3 \
--tool-call-parser qwen3_coder \
--enable-auto-tool-choice \
--enable-prefix-caching \
--enable-chunked-prefill
```

> [!NOTE]
> Bắt buộc phải có `--enable-auto-tool-choice` đi kèm `--tool-call-parser qwen3_coder` thì vLLM mới chấp nhận request có `tools`. Trong stream SSE, reasoning delta xuất hiện trước và tool calls delta xuất hiện sau khi thinking hoàn tất.

### Vệ Sinh Tương Thích tại LiteLLM Gateway
- LiteLLM chuyển tiếp các tham số lạ sang `extra_body`.
- Khóa `tool_call_parser: openai` trong `litellm_config.yaml` là **dead config** đối với vLLM. Việc loại bỏ khóa này trên model `rag-core` là để bảo đảm vệ sinh tương thích phòng ngừa vLLM phiên bản sau kích hoạt `extra: forbid`.

---

## 3. Quản Lý Thinking Token & Phòng Thủ Cache

Theo chuẩn mực **RULE-5.8**:
- Khi cần trích xuất JSON hoặc sinh HyDE queries, BẮT BUỘC gọi qua alias `local-instruct` hoặc gửi:
  ```json
  {
    "chat_template_kwargs": {
      "enable_thinking": false
    }
  }
  ```
- Không bao giờ dựa vào system prompt để yêu cầu mô hình reasoning ngừng suy nghĩ.

> [!WARNING]
> **Cảnh báo Bẫy Redis Cache**:
> LiteLLM Redis Cache (DB 0, TTL 3600) **KHÔNG** đưa `chat_template_kwargs` vào khóa băm cache. Nếu một prompt vừa bị starvation dưới thinking bật, lần gọi sau dù đổi sang `enable_thinking: False` vẫn có thể trúng lại response rỗng cũ. Do đó, khi retry phải gửi kèm `caching: false` hoặc cơ chế cache-bust.

---

## 4. Kiểm Tra Sức Khỏe & Giám Sát Tài Nguyên (Health Check)

```bash
# 1. Kiểm tra nhanh trạng thái các containers
docker ps -a --filter "name=qwen" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 2. Kiểm tra endpoint readiness
curl -s http://localhost:8004/v1/models | jq

# 3. Kiểm tra qua AI Gateway (Functional Alias)
curl -s http://localhost:8090/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq

# 4. Kiểm tra metrics hiệu năng vLLM (Prometheus endpoint)
curl -s http://localhost:8004/metrics
```

### Các chỉ số Prometheus chuẩn hóa (vLLM 0.26+)
- `vllm:num_requests_running`: Số lượng request đang xử lý đồng thời.
- `vllm:kv_cache_usage_perc`: Tỷ lệ sử dụng bộ nhớ KV Cache (Gauge từ 0.0 đến 1.0, ngưỡng cảnh báo `0.95`).
- `vllm:generation_tokens_total`: Tổng số tokens sinh ra (Counter tích lũy).

---

## 5. Xử Lý Sự Cố Thường Gặp (Troubleshooting)

### Sự cố 1: Container bị Out of Memory (OOM) hoặc VRAM Fragmented
```bash
# Khởi động lại container 35B để giải phóng KV cache
docker restart qwen36b
# Kiểm tra bộ nhớ thống nhất qua memory footprint
nvidia-smi --query-compute-apps=process_name,used_memory --format=csv
```

### Sự cố 2: Thinking Token Starvation (JSON / Tool Call trả về rỗng)
- **Hiện tượng**: `finish_reason: "length"`, `content: None` hoặc `""`, tool calls bị nuốt chửng do token reasoning dùng hết `max_tokens`.
- **Khắc phục**: Chuyển sang gọi model alias `local-instruct` hoặc gửi `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` kèm `caching: false`.
