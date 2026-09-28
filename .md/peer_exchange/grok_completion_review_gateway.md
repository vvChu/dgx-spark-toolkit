# Nghiệm thu hoàn thành — AI-Gateway Qwen 3.6

Ngày: 2026-09-28. Đối chiếu với sáu mandate trong `.md/peer_exchange/grok_cross_review_gateway_plan.md` và walkthrough của Antigravity. Không restart container trong vòng này. Không `FLUSHDB`.

## Phán quyết

**FINAL APPROVE**

Sáu mandate đã có trong cây mã đang chạy và trên runtime `:8090`. `python3 scripts/verify_gateway_models.py` thoát 0, 5/5 kịch bản pass.

## Mandate

| # | Yêu cầu | Kết quả kiểm |
|---|---|---|
| 1 | `rag-core` có `enable_thinking: false`, không có `tool_call_parser` | Có ở `litellm_config.yaml` dòng 1043–1045. `grep tool_call_parser` trên file này ra 0. |
| 2 | `local-coder` và `qwen-local-primary` khai báo `enable_thinking: true` | Có ở dòng 1089–1090 và 1153–1155. |
| 3 | Stream và chat không ép thinking cho `rag-core` | `AIGatewayClient.stream` chỉ bật thinking cho `qwen-local-primary`, `local-coder`, hoặc tên chứa `primary` / `coder`. `ChatService._generate_answer` dùng cùng điều kiện tên. `extract_json` vẫn ép `false`. |
| 4 | Restart riêng gateway, namespace cache, không `FLUSHALL` | `ai-gateway` up khoảng 4 phút lúc bắt đầu kiểm. `qwen36b` vẫn up 7 giờ. `cache_params.namespace` là `v20260928_qwen36_nonthinking`. DB 1 vẫn 3 key, DB 2 và DB 4 mỗi DB 1 key. |
| 5 | Script live chốt `finish_reason`, content, reasoning | Chạy lại trên `:8090`, thoát 0. Chi tiết bên dưới. |
| 6 | Đồng bộ sang Hub | `Pattern 16` và `vllm-manager: true` đã có trong HEAD. Container mount đúng file này. |

## Kết quả `scripts/verify_gateway_models.py`

| Kịch bản | Đo được | Kết luận |
|---|---|---|
| 1 `rag-core`, max_tokens 100 | 0,024s, `stop`, content `{"status": "ok"}`, reasoning 0 | PASS |
| 2 `local-instruct`, max_tokens 100 | 0,014s, `stop`, content không rỗng, reasoning 0 | PASS |
| 3 `local-coder`, max_tokens 512 | 0,009s, `tool_calls`, hàm `tra_cuu_luat_xay_dung` | PASS |
| 4 `qwen-local-primary`, max_tokens 512 | 0,009s, `length`, reasoning 1712 ký tự, content 530 ký tự | PASS |
| 5 cache | `stop`, content không rỗng, header `x-litellm-cache-key` bắt đầu bằng `v20260928_qwen36_nonthinking:` | PASS |

Bốn kịch bản đầu trả về trong 9–24ms nên là cache hit của chính namespace mới, không phải lần sinh GPU mới. Bản cache đúng hợp đồng: `rag-core` không reasoning, `qwen-local-primary` giữ 1712 ký tự CoT như walkthrough đã ghi. Sau script, Redis DB 0 có 22 key mang prefix namespace (trước script là 6). Key cũ không prefix vẫn còn và tự hết hạn theo TTL.

## Phần còn lại, không chặn nghiệm thu

- Điều kiện `"primary" in name` cũng khớp `ocr-primary` nếu tên đó đi vào stream. Chuỗi mặc định không gồm model đó. (Đã khắc phục: `qwen` and `primary`)
- Chat mặc định vẫn là `settings.VLLM_MODEL` = `rag-core`, nên chat mặc định không suy luận. CoT chỉ bật khi caller chọn model có `primary` hoặc `coder` trong tên.
- Script kịch bản 5 không so hai response cùng prompt với thinking bật và tắt. Namespace đã cách ly key cũ. Bên trong namespace, hash cache của LiteLLM 1.83.3 vẫn không gồm `chat_template_kwargs`.
- File script có default trùng khóa đã nằm trong 36 file tracked khác. Nên đọc khóa từ môi trường khi commit file này.
