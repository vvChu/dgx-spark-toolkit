# Hướng Dẫn Truy Cập Từ Xa (Remote Access)

Tài liệu này hướng dẫn cách kết nối từ máy cá nhân tới các dịch vụ AI trên Server Spark.

## 1. Thông Tin Server (Spark)

| | |
|---|---|
| **IP Nội bộ** | `192.168.1.27` |
| **IP VPN/Tailscale** | `100.83.192.30` |
| **AI Gateway** | port `8090` |
| **API Key** | `sk-spark-secure-key-2026` |

---

## 2. Mở Firewall (Chạy 1 lần trên Server)

```bash
sudo bash /home/vvc/Codebase/dgx-spark-toolkit/scripts/setup-remote-access.sh
```

---

## 3. Kết Nối Từ Client

### Cách A: Trực tiếp (cùng LAN hoặc Tailscale)

```bash
curl http://100.83.192.30:8090/v1/models \
  -H "Authorization: Bearer sk-spark-secure-key-2026"
```

### Cách B: SSH Tunneling (qua Firewall)

```bash
# Chạy trên máy Client:
ssh -L 8090:localhost:8090 vvc@192.168.1.27

# Sau đó dùng localhost:
curl http://localhost:8090/v1/models \
  -H "Authorization: Bearer sk-spark-secure-key-2026"
```

---

## 4. Sử Dụng Trong Code

**Python (OpenAI SDK):**
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://100.83.192.30:8090/v1",
    api_key="sk-spark-secure-key-2026"
)

# Dùng bất kỳ model nào trong 25 models
response = client.chat.completions.create(
    model="claude-sonnet-4-6",   # hoặc gemini-3-flash, qwen3.5-35b, gpt-4o...
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

**Frontend (.env):**
```env
VITE_AI_GATEWAY_URL=http://100.83.192.30:8090/v1
VITE_AI_GATEWAY_KEY=sk-spark-secure-key-2026
```
