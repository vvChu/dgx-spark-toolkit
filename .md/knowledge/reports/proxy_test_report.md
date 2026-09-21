# 📊 Báo Cáo Kiểm Tra Kết Nối Model Tại API Proxy

- **Thời gian kiểm tra**: 2026-09-08 17:14:38
- **Proxy Endpoint**: `http://100.83.192.30:8045/v1`
- **Tổng số model**: 91
- **Thành công (200 OK)**: 19
- **Lỗi / Timeout**: 72

## 1. Danh sách Model Kết Nối Thành Công (200 OK)

| STT | Model ID | Latency | Phản hồi mẫu |
| :--- | :--- | :--- | :--- |
| 1 | `claude-3-5-sonnet-20240620` | 7349ms | `Hi! How can I` |
| 2 | `claude-3-5-sonnet-20241022` | 3230ms | `Hi! How can I` |
| 3 | `claude-3-haiku-20240307` | 2501ms | `Hi! I'm` |
| 4 | `claude-haiku-4` | 2243ms | `Hi! How can I` |
| 5 | `claude-haiku-4-5-20251001` | 2129ms | `Hi! How can I` |
| 6 | `claude-opus-4-5-20251101` | 6667ms | `Hi there! 👋 I'm Antigravity, your AI cod` |
| 7 | `claude-opus-4-6-20260201` | 7159ms | `Hi there! 👋 I'm Antigravity, your AI cod` |
| 8 | `claude-opus-4-6-thinking` | 5418ms | `Hi there! 👋 I'm Antigravity, your AI cod` |
| 9 | `claude-opus-4.6-thinking` | 5336ms | `Hi there! 👋 I'm Antigravity, your AI cod` |
| 10 | `claude-sonnet-4-5` | 5169ms | `Hi! How can I` |
| 11 | `claude-sonnet-4-6` | 2801ms | `Hi! I'm Antigravity, your AI coding assi` |
| 12 | `gemini-2.5-flash` | 2518ms | `Hello! I'm Antigravity, your agentic AI ` |
| 13 | `gemini-2.5-flash-lite` | 2870ms | `Hello! I am Antigravity. I'm ready to as` |
| 14 | `gemini-2.5-flash-thinking` | 3496ms | `Hello! I am Antigravity, your agentic AI` |
| 15 | `gemini-3-flash` | 2768ms | `Gemini 3.5 Flash is no longer available.` |
| 16 | `gemini-3-flash-agent` | 580ms | `Gemini 3.5 Flash is no longer available.` |
| 17 | `gemini-3-pro` | 4398ms | `Hello! I'm Antigravity, an AI coding ass` |
| 18 | `gemini-3-pro-high` | 5300ms | `Hi there! I'm Antigravity, an agentic AI` |
| 19 | `gemini-3-pro-low` | 4000ms | `Hello! I'm Antigravity. How can I help y` |

## 2. Danh sách Model Không Khả Dụng / Lỗi

| STT | Model ID | HTTP Code | Latency | Chi tiết lỗi |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `claude` | 408 | 8011ms | Timeout (>8s) |
| 2 | `claude-opus-4` | 408 | 8006ms | Timeout (>8s) |
| 3 | `claude-opus-4-5-thinking` | 408 | 8010ms | Timeout (>8s) |
| 4 | `claude-opus-4-6` | 408 | 8009ms | Timeout (>8s) |
| 5 | `claude-opus-4.6` | 408 | 8008ms | Timeout (>8s) |
| 6 | `claude-sonnet-4-5-20250929` | 408 | 8004ms | Timeout (>8s) |
| 7 | `claude-sonnet-4-5-thinking` | 408 | 8005ms | Timeout (>8s) |
| 8 | `claude-sonnet-4-6-thinking` | 408 | 8009ms | Timeout (>8s) |
| 9 | `gemini-2.0-flash-exp` | 503 | 6198ms | Token error: All accounts limited. Wait 19s. |
| 10 | `gemini-2.5-pro` | 503 | 6733ms | Token error: All accounts limited. Wait 16s. |
| 11 | `gemini-3-pro-image` | 503 | 1ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 12 | `gemini-3-pro-image-16x9` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 13 | `gemini-3-pro-image-1x1` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 14 | `gemini-3-pro-image-21x9` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 15 | `gemini-3-pro-image-2k` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 16 | `gemini-3-pro-image-2k-16x9` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 17 | `gemini-3-pro-image-2k-1x1` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 18 | `gemini-3-pro-image-2k-21x9` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 19 | `gemini-3-pro-image-2k-3x4` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 20 | `gemini-3-pro-image-2k-4x3` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 21 | `gemini-3-pro-image-2k-9x16` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 22 | `gemini-3-pro-image-3x4` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 23 | `gemini-3-pro-image-4k` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 24 | `gemini-3-pro-image-4k-16x9` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 25 | `gemini-3-pro-image-4k-1x1` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 26 | `gemini-3-pro-image-4k-21x9` | 503 | 1ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 27 | `gemini-3-pro-image-4k-3x4` | 503 | 1ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 28 | `gemini-3-pro-image-4k-4x3` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 29 | `gemini-3-pro-image-4k-9x16` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 30 | `gemini-3-pro-image-4x3` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 31 | `gemini-3-pro-image-9x16` | 503 | 0ms | Token error: No accounts available with quota for model: gemini-3-pro-image |
| 32 | `gemini-3-pro-preview` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 33 | `gemini-3.1-flash-image` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 34 | `gemini-3.1-flash-lite` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 35 | `gemini-3.1-pro` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 36 | `gemini-3.1-pro-high` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 37 | `gemini-3.1-pro-low` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 38 | `gemini-3.1-pro-preview` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 39 | `gemini-3.5-flash-extra-low` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 40 | `gemini-3.5-flash-lite` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 41 | `gemini-3.5-flash-low` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 42 | `gemini-3.6-flash-high` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 43 | `gemini-3.6-flash-low` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 44 | `gemini-3.6-flash-medium` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 45 | `gemini-3.6-flash-tiered` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 46 | `gemini-3.7-flash-high` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 47 | `gemini-3.7-flash-low` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 48 | `gemini-3.7-flash-medium` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 49 | `gemini-3.7-flash-tiered` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 50 | `gemini-3.8-flash-high` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 51 | `gemini-3.8-flash-low` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 52 | `gemini-3.8-flash-medium` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 53 | `gemini-3.8-flash-tiered` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 54 | `gemini-pro-agent` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 55 | `gpt-3.5-turbo` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 56 | `gpt-3.5-turbo-0125` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 57 | `gpt-3.5-turbo-0613` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 58 | `gpt-3.5-turbo-1106` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 59 | `gpt-3.5-turbo-16k` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 60 | `gpt-4` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 61 | `gpt-4-0125-preview` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 62 | `gpt-4-0613` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 63 | `gpt-4-1106-preview` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 64 | `gpt-4-turbo` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 65 | `gpt-4-turbo-preview` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 66 | `gpt-4o` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 67 | `gpt-4o-2024-05-13` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 68 | `gpt-4o-2024-08-06` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 69 | `gpt-4o-mini` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 70 | `gpt-4o-mini-2024-07-18` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 71 | `gpt-oss-120b-medium` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
| 72 | `internal-background-task` | 503 | 1ms | Token error: All accounts limited. Wait 20s. |
