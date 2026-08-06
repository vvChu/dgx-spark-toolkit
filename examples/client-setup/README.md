# 🚀 AI Gateway — Client Setup Package

Bộ file cấu hình sẵn dùng để kết nối project từ máy khác tới AI Gateway trên DGX Spark.

## Nội Dung

| File | Mô Tả |
|------|--------|
| `.env.ai-gateway` | Template biến môi trường — copy vào project rồi đổi tên `.env` |
| `test-connection.sh` | Script kiểm tra kết nối từ máy client |
| `ai_client.py` | Python module sẵn dùng — `from ai_client import chat` |
| `ai-client.ts` | TypeScript module sẵn dùng — `import { chat } from './ai-client'` |

## Quick Start (3 bước)

### 1. Copy `.env` vào project
```bash
cp .env.ai-gateway /path/to/your/project/.env
```

### 2. Cài SDK
```bash
# Python
pip install openai python-dotenv

# Node.js
npm install openai dotenv
```

### 3. Sử dụng
```python
from ai_client import chat
reply = chat("Xin chào!")   # → Qwen 3.5 35B (local, private)
```

## Kiểm Tra Kết Nối

```bash
bash test-connection.sh              # Mặc định: Tailscale IP
bash test-connection.sh 192.168.1.X  # Dùng IP LAN
bash test-connection.sh localhost     # Dùng SSH tunnel
```

## Hướng Dẫn Chi Tiết

Xem: [`playbooks/client-setup-guide.md`](../playbooks/client-setup-guide.md)
