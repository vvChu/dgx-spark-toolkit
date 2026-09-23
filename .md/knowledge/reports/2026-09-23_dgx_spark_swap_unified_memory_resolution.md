# Biên Bản Quyết Định Kiến Trúc: Tối Ưu Hóa Bộ Nhớ Unified Memory & Triệt Tiêu Nguy Cơ Tràn Swap Trên DGX Spark

- **Thời gian**: 2026-09-23
- **Phương thức**: `/ccba-grilling` (Stress-Test Design Loop & Double-Pass Adversarial Review)
- **Hệ thống**: NVIDIA DGX Spark (Blackwell GB10, 128GB LPDDR5X Unified Memory)
- **Tham gia**: Người dùng & CCBA AI Assistant

---

## 1. Bối cảnh & Vấn đề Ban đầu
Người dùng nhận thấy mức tiêu thụ Swap trên DGX Spark chạm ngưỡng báo động (**13GiB / 15GiB**) và đưa ra đề xuất:
> *"DGX Spark đang chịu tải nhiều dịch vụ ngoài RAG. Cần đội ngũ hạ tầng kiểm tra và dọn dẹp bộ nhớ Swap định kỳ để tránh nguy cơ sập đột ngột khi vLLM nhận tải lớn."*

Qua quy trình rà quét mã nguồn và đo lường trực tiếp nhân Linux (Vòng 1 - Code-First Research), Agent phát hiện:
1. **Tổng RAM vật lý**: 121 GiB khả dụng, nhưng **107 GiB** đã bị chiếm dụng; dung lượng Free chỉ còn **3.1 GiB** `[đo thực tế: free -h]`.
2. **vLLM Engine**: Đang ghim cứng **90,293 MiB (~88.17 GiB)** RAM vật lý `[đo thực tế: nvidia-smi]`, trong đó có **50.41 GiB** chỉ để dự trữ vùng đệm KV Cache rỗng (`GPU KV cache usage: 0.0%` `[đo thực tế: vllm logs]`) do thiết lập `LOCAL_PRIMARY_GPU_UTIL=0.75` trong `.env`.
3. **Ảo tưởng xả Swap (`swapoff`)**: Với chỉ 3.1 GiB RAM trống, bất kỳ thao tác nào nhằm xả 5.3GiB–13GiB Swap ngược lại vào RAM sẽ **lập tức kích hoạt Linux OOM-Killer bắn hạ `vLLM` hoặc `Milvus`**.
4. **Nguy cơ thực tế của vLLM**: Không phải sập vì hết swap, mà bị **1.31 GiB bộ nhớ vLLM trôi vào swap đĩa cứng**, gây ra **Latency Cliff (vách đá trễ I/O)** khi có tải lớn.
5. **Dịch vụ chạy ngầm không giới hạn**: Container `milvus-standalone`, `neo4j-graph`, `open-webui` không có memory limit trong Docker Compose; kèm theo 1 dịch vụ `ocr_server.service` trên host chạy song song với `dgx-spark-ocr-worker` trong Docker.

---

## 2. Kết Quả Phỏng Vấn Socrates (`/ccba-grilling`) & Quyết Định Đã Chốt

### Vòng 1 — Bản chất Vấn đề & Triệt tiêu Rủi ro OOM
- **Chất vấn**: Đội hạ tầng có nhận thức được việc chạy lệnh xả Swap định kỳ là "cò súng" kích hoạt OOM-Killer không?
- **Quyết định (Chốt)**: **ĐỒNG Ý LOẠI BỎ HOÀN TOÀN** việc xả Swap thủ công/định kỳ. Chuyển hướng sang giải quyết tận gốc nguyên nhân cạnh tranh bộ nhớ Unified Memory.

### Vòng 2 — Tái phân bổ Unified Memory cho vLLM
- **Chất vấn**: vLLM đang xí trước 50.41 GiB KV Cache (phục vụ 25 luồng 98k context cùng lúc) nhưng thực tế dùng 0.0%, gây nghẹt thở cho toàn hệ thống.
- **Quyết định (Chốt)**: Chọn **Phương án A (Balanced Pro)**:
  - Hạ `LOCAL_PRIMARY_GPU_UTIL` từ `0.75` xuống **`0.60`**.
  - Giữ nguyên `LOCAL_PRIMARY_MAX_MODEL_LEN=98304`.
  - **Kết quả**: vLLM chỉ chiếm ~72.6 GiB (40.3 GiB model + ~32.3 GiB KV Cache, vẫn đủ sức gánh 16 luồng 98k context hoặc 48 luồng 32k context).
  - **Thu hồi ngay**: **~18.7 GiB RAM vật lý** cho hệ điều hành và các container.

### Vòng 3 — Thiết Quân Luật Tài Nguyên (Hard Cgroup Limits) & Tối Ưu OS
- **Chất vấn**: Dịch vụ ngoài RAG và các container thả nổi không giới hạn RAM có thể tái diễn kịch bản tràn Swap.
- **Quyết định (Chốt)**: **ĐỒNG Ý TRIỂN KHAI TOÀN BỘ**:
  1. Gán trần cứng `deploy.resources.limits.memory` trong `docker-compose.yml`:
     - `vllm-36b`: max **78G**
     - `milvus-standalone`: max **8G**
     - `neo4j-graph`: max **4G** (JVM heap max 2G)
     - `open-webui`: max **2G**
  2. Tạo script `scripts/tune_dgx_spark_os.sh` để:
     - Đặt `vm.swappiness = 10` vĩnh viễn (ngăn kernel swap bừa bãi).
     - Mở rộng Swap an toàn từ 16GB lên **32GB** trên ổ NVMe (tận dụng 814GB đĩa trống).
     - Tắt và vô hiệu hóa dịch vụ OCR thừa trên host (`ocr_server.service`).

---

## 3. Danh Mục Tệp Thay Đổi
1. [.env](file:///home/vvc/Codebase/dgx-spark-toolkit/.env): `LOCAL_PRIMARY_GPU_UTIL=0.60`
2. [docker-compose.yml](file:///home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml): Cập nhật giới hạn deploy resources cho `vllm-36b`, `milvus-standalone`, `neo4j`, `open-webui`.
3. [scripts/tune_dgx_spark_os.sh](file:///home/vvc/Codebase/dgx-spark-toolkit/scripts/tune_dgx_spark_os.sh): Script tự động hóa cho đội hạ tầng (sudo).
4. [.md/knowledge/reports/2026-09-23_dgx_spark_swap_unified_memory_resolution.md](file:///home/vvc/Codebase/dgx-spark-toolkit/.md/knowledge/reports/2026-09-23_dgx_spark_swap_unified_memory_resolution.md): Biên bản lưu trữ này.
