---
name: pr-copilot-flow
command: /pr-copilot-flow
description: Tự động kiểm tra Copilot review, sửa code, lưu bài học kinh nghiệm, push PR, chờ CI xanh và thực hiện merge PR.
type: workflow
category: custom
enabled: true
version: v1.0
---

# 🤖 /pr-copilot-flow Workflow

Workflow tự động hóa toàn bộ quy trình kiểm thử và merge PR an toàn:
1. Quét comments/reviews từ Copilot Code Reviewer trên PR
2. Sửa mã nguồn & kiểm thử unit tests local (Pass 100%)
3. Lưu bài học kinh nghiệm vào `.agents/rules/codebase-engineering-rules.md`
4. Commit & Push cập nhật lên PR
5. Chờ CI Checks xanh 100%
6. Thực hiện Merge PR tự động (`gh pr merge --squash --delete-branch`)

---

## Bước 1 — Quét Copilot Review & Comments

```bash
PR_ID="${1:-28}"
echo "🔍 Checking Copilot reviews & comments for PR #${PR_ID}..."
gh api repos/:owner/:repo/pulls/${PR_ID}/reviews --jq '.[] | {user: .user.login, state: .state, body: .body}'
gh api repos/:owner/:repo/pulls/${PR_ID}/comments --jq '.[] | {path: .path, line: .line, body: .body}'
```

## Bước 2 — Khắc phục Code & Chạy Kiểm thử Unit Test

- Đọc các vị trí file và dòng code bị cảnh báo
- Tiến hành chỉnh sửa mã nguồn
- Chạy kiểm thử tự động local:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service
PYTHONPATH=. /home/vvc/.local/bin/uv run pytest tests/ -q
flake8 services/rag-service/
```

## Bước 3 — Tự động lưu Bài học Kinh nghiệm

Bổ sung các quy tắc kỹ thuật mới đúc kết từ Copilot review vào file persistent rules:
`file:///home/vvc/Codebase/dgx-spark-toolkit/.agents/rules/codebase-engineering-rules.md`

## Bước 4 — Commit & Push Cập nhật PR

```bash
git add .
git commit -m "fix(copilot-review): address copilot feedback and update persistent rules"
git push origin HEAD
```

## Bước 5 — Chờ CI Status Check Xanh (Watch CI)

```bash
PR_ID="${1:-28}"
echo "⏳ Waiting for GitHub Actions CI checks to pass..."
gh pr checks ${PR_ID} --watch
```

## Bước 6 — Tự động Merge PR

Khi toàn bộ status checks hiển thị `SUCCESS`:
```bash
PR_ID="${1:-28}"
echo "🚀 All CI checks passed! Merging PR #${PR_ID}..."
gh pr merge ${PR_ID} --squash --delete-branch
```
