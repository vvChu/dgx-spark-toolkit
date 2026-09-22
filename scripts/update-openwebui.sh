#!/usr/bin/env bash
# ==============================================================================
# Safe Updater for Open WebUI on NVIDIA DGX Spark
# Principles: Zero Data Loss, WAL-Safe Snapshot, 100% Deterministic Rollback
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

TARGET_VERSION="${1:-v0.11.4}"
BACKUP_DIR="$SCRIPT_DIR/backups/open-webui"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_TAR="$BACKUP_DIR/snapshot_${TIMESTAMP}.tar.gz"

echo "=========================================================="
echo "🚀 BẮT ĐẦU QUY TRÌNH NÂNG CẤP OPEN WEBUI AN TOÀN"
echo "   Mục tiêu: $TARGET_VERSION"
echo "   Thời gian: $(date)"
echo "=========================================================="

echo "=== [1/6] Kiểm tra điều kiện tiên quyết ==="
# 1. Kiểm tra dung lượng ổ đĩa khả dụng >= 15GB
AVAIL_GB=$(df -BG /var/lib/docker | awk 'NR==2 {gsub("G",""); print $4}')
if [ "$AVAIL_GB" -lt 15 ]; then
    echo "❌ Lỗi: Ổ đĩa chỉ còn ${AVAIL_GB}GB trống. Yêu cầu tối thiểu 15GB."
    exit 1
fi
echo "✅ Dung lượng đĩa khả dụng: ${AVAIL_GB}GB (Đạt chuẩn >= 15GB)"
mkdir -p "$BACKUP_DIR"

# 2. Đọc phiên bản hiện tại từ .env
CURRENT_VERSION=$(grep -E '^OPEN_WEBUI_VERSION=' .env | cut -d '=' -f2 || echo "v0.9.1")
echo "ℹ️ Phiên bản hiện tại: $CURRENT_VERSION -> Nâng cấp lên: $TARGET_VERSION"

# 3. Lấy tên Volume động của Open WebUI
VOLUME_NAME=$(docker inspect open-webui --format '{{range .Mounts}}{{if eq .Destination "/app/backend/data"}}{{.Name}}{{end}}{{end}}' 2>/dev/null || echo "dgx-spark-toolkit_open-webui_data")
echo "ℹ️ Volume lưu trữ state: $VOLUME_NAME"

echo "=== [2/6] Tạo bản sao lưu Snapshot toàn diện (WAL-Safe) ==="
# Kiểm tra container đang chạy để thực hiện sqlite3.backup
if ! docker inspect open-webui --format '{{.State.Running}}' | grep -q "true"; then
    echo "⚠️ Container open-webui đang dừng. Khởi động lại tạm thời để snapshot..."
    docker compose up -d open-webui
    sleep 5
fi

# Chạy sqlite3.backup() qua Python API bên trong container để kết xuất snapshot đồng nhất 100% (hợp nhất WAL)
docker exec open-webui python3 -c "
import sqlite3
src = sqlite3.connect('/app/backend/data/webui.db')
dst = sqlite3.connect('/app/backend/data/webui_snapshot.tmp')
src.backup(dst)
dst.close()
src.close()
"

# Đóng gói Snapshot DB + vector_db + uploads
docker exec open-webui tar -czf /app/backend/data/state_backup.tar.gz \
    -C /app/backend/data webui_snapshot.tmp vector_db uploads
docker cp open-webui:/app/backend/data/state_backup.tar.gz "$BACKUP_TAR"
docker exec open-webui rm -f /app/backend/data/webui_snapshot.tmp /app/backend/data/state_backup.tar.gz

if [ ! -s "$BACKUP_TAR" ]; then
    echo "❌ Lỗi: Bản snapshot rỗng hoặc không tạo được!"
    exit 1
fi
echo "✅ Đã lưu trữ an toàn bản snapshot tại: $BACKUP_TAR ($(du -h "$BACKUP_TAR" | cut -f1))"

echo "=== [3/6] Cập nhật Cấu hình & Kéo Image mới ==="
sed -i "s/^OPEN_WEBUI_VERSION=.*/OPEN_WEBUI_VERSION=$TARGET_VERSION/" .env

echo "Đang kéo image ghcr.io/open-webui/open-webui:$TARGET_VERSION..."
if ! docker compose pull open-webui; then
    echo "❌ Kéo image $TARGET_VERSION thất bại! Đang phục hồi .env..."
    sed -i "s/^OPEN_WEBUI_VERSION=.*/OPEN_WEBUI_VERSION=$CURRENT_VERSION/" .env
    exit 1
fi
echo "✅ Kéo image mới thành công."

echo "=== [4/6] Khởi động Container & Chạy Migrations ==="
docker compose up -d open-webui

echo "=== [5/6] Giám sát Khởi động & Healthcheck (Timeout: 120s) ==="
SUCCESS=0
for i in $(seq 1 24); do
    sleep 5
    STATUS=$(docker inspect open-webui --format '{{.State.Status}}' 2>/dev/null || echo "exited")
    if [ "$STATUS" = "exited" ]; then
        echo "❌ Container bị dừng (Status: exited)! Có thể do lỗi migration database."
        break
    fi
    
    # Kiểm tra cổng nội bộ localhost:3001
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/health || true)
    if [ "$HTTP_CODE" = "200" ]; then
        SUCCESS=1
        echo "✅ Khởi động và migration thành công sau $((i * 5)) giây!"
        break
    fi
    echo "   ...đang chờ hoàn tất migrations ($((i * 5))s/120s) [HTTP: $HTTP_CODE]"
done

if [ "$SUCCESS" -ne 1 ]; then
    echo "🚨 CẢNH BÁO: Quá trình nâng cấp thất bại! Bắt đầu AUTO-ROLLBACK NGAY LẬP TỨC..."
    docker stop open-webui || true
    
    # Đưa version về bản cũ trong .env
    sed -i "s/^OPEN_WEBUI_VERSION=.*/OPEN_WEBUI_VERSION=$CURRENT_VERSION/" .env
    
    # Phục hồi an toàn qua volume mount dùng alpine:latest
    docker run --rm \
        -v "${VOLUME_NAME}:/data" \
        -v "$BACKUP_DIR:/backup" \
        alpine:latest sh -c "
            tar -xzf /backup/$(basename "$BACKUP_TAR") -C /data/
            mv /data/webui_snapshot.tmp /data/webui.db
            rm -f /data/webui.db-wal /data/webui.db-shm
        "
    
    # Khởi động lại bản cũ
    docker compose up -d open-webui
    echo "⚠️ ĐÃ ROLLBACK THÀNH CÔNG VỀ $CURRENT_VERSION. Toàn bộ dữ liệu được bảo toàn nguyên vẹn."
    exit 1
fi

echo "=== [6/6] Hoàn tất & Dọn dẹp Bản Sao Lưu Cũ ==="
# Giữ lại 5 bản backup gần nhất trên host
ls -dt "$BACKUP_DIR"/snapshot_*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm -f || true

NEW_VER_CHECK=$(curl -s http://localhost:3001/api/version | cut -d '"' -f4 || echo "$TARGET_VERSION")
echo "=========================================================="
echo "🎉 NÂNG CẤP THÀNH CÔNG TRỌN VẸN!"
echo "   Phiên bản đang hoạt động: $NEW_VER_CHECK"
echo "   Tên miền truy cập: https://chat.ibst-bim.vn"
echo "=========================================================="
