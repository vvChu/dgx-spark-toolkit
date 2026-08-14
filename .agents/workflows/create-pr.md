---
name: create-pr
command: /create-pr
description: Tự động hóa quy trình tạo Feature Branch, chạy kiểm thử Pre-flight, push origin và mở Pull Request trên GitHub.
type: workflow
category: custom
enabled: true
version: v1.0
---

# 🚀 /create-pr Workflow

Workflow tạo Feature Branch, kiểm thử cục bộ và mở Pull Request chuẩn quy ước:

1. Xác định loại branch và tên branch (`<type>/<short-description>`).
2. Tạo và chuyển sang branch mới từ `master`.
3. Chạy kiểm thử Pre-flight (Flake8 lint + Pytest unit tests).
4. Commit các thay đổi theo Conventional Commits: `type(scope): description`.
5. Push branch lên remote (`git push -u origin <branch-name>`).
6. Mở Pull Request lên `master` qua GitHub CLI (`gh pr create`).
7. Tự động chuyển giao sang `/pr-copilot-flow` để giám sát CI & merge.

---

## Bước 1 — Tạo Feature Branch

Tuân thủ quy ước đặt tên branch:
- `feat/<name>`: Tính năng mới
- `fix/<name>`: Sửa lỗi
- `docs/<name>`: Cập nhật tài liệu
- `refactor/<name>`: Tái cấu trúc code
- `test/<name>`: Thêm hoặc sửa test

```bash
BRANCH_NAME="${1:-feat/new-feature}"
git checkout master
git pull origin master
git checkout -b "${BRANCH_NAME}"
```

## Bước 2 — Chạy Kiểm thử Pre-flight Local

Đảm bảo mã nguồn đạt chuẩn trước khi commit và push:
```bash
# 1. Linting RAG service
flake8 services/rag-service/ --config=services/rag-service/.flake8

# 2. Chạy Backend unit tests
cd /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service
pytest tests/test_config.py -v
```

## Bước 3 — Commit Thay đổi

```bash
# Format commit: type(scope): description
git add <files>
git commit -m "<type>(<scope>): <description>"
```

## Bước 4 — Push Branch lên Remote

```bash
git push -u origin HEAD
```

## Bước 5 — Mở Pull Request trên GitHub

```bash
PR_TITLE="${2:-<type>(<scope>): <description>}"
PR_BODY="${3:-Summary of changes and motivation.}"

gh pr create \
  --base master \
  --head "$(git branch --show-current)" \
  --title "${PR_TITLE}" \
  --body "${PR_BODY}"
```

## Bước 6 — Bước tiếp theo

Sau khi PR được tạo thành công, kích hoạt `/pr-copilot-flow` để:
1. Theo dõi Copilot Code Review.
2. Kiểm tra GitHub Actions CI checks (`gh pr checks --watch`).
3. Tự động merge khi CI xanh 100% (`gh pr merge --squash --delete-branch`).
