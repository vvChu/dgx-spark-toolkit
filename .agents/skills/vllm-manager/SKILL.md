---
name: vllm-manager
description: (Legacy Pointer) Quản trị mô hình vLLM trên DGX Spark. Trỏ tới canonical skill ccba-vllm-manager.
---

# vLLM Manager (Pointer)

> [!NOTE]
> Kỹ năng chuẩn hóa chính thức đã được chuyển tiếp sang **[ccba-vllm-manager](file:///home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/ccba-vllm-manager/SKILL.md)** tuân thủ quy chuẩn không gian tên CCBA (ADR-0056 / ADR-0057).
> Vui lòng tham chiếu [ccba-vllm-manager/SKILL.md](file:///home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/ccba-vllm-manager/SKILL.md) để xem toàn bộ kiến trúc, AOT Inductor Cache, Dual Parser, và hướng dẫn vận hành cho Qwen 3.6 35B trên NVIDIA DGX Spark.

## Spoke-Local Scripts

Thư mục `./scripts/` cục bộ chứa các tiện ích vận hành của Spoke:
- `scripts/health_monitor.py`: Giám sát sức khỏe container vLLM và bộ nhớ cache.
- `scripts/workflow_optimizer.py`: Tối ưu hóa workflow và kiểm tra cấu hình.
- `scripts/benchmark_vllm.py`: Đo kiểm throughput và latency suy luận cục bộ.
