#!/usr/bin/env bash
# ==============================================================================
# DGX Spark OS Performance & Swap Optimization Script
# Author: CCBA AI Platform & Infrastructure Engineering
# Purpose: Tune Linux Kernel parameters, expand Swap to 32GB on NVMe safely,
#          and disable redundant host OCR background services.
# Usage: sudo bash scripts/tune_dgx_spark_os.sh
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== [1/4] Checking Root Permissions ===${NC}"
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Lỗi: Vui lòng chạy script này với quyền sudo (sudo bash scripts/tune_dgx_spark_os.sh)${NC}"
  exit 1
fi

echo -e "${GREEN}Đã xác thực quyền root.${NC}"

# ------------------------------------------------------------------------------
# 1. Tinh chỉnh Linux Kernel Swappiness & Cache Pressure
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}=== [2/4] Cấu hình Linux Kernel (vm.swappiness=10) ===${NC}"
SYSCTL_CONF="/etc/sysctl.d/99-dgx-spark.conf"

cat << 'EOF' > "$SYSCTL_CONF"
# DGX Spark AI Production Tuning (GB10 Unified Memory)
# Keep active application memory in RAM, reduce aggressive swapping
vm.swappiness = 10

# Balance between directory/inode cache and page cache
vm.vfs_cache_pressure = 50

# Ensure memory overcommit does not arbitrarily trigger OOM
vm.overcommit_memory = 0
EOF

sysctl --system > /dev/null 2>&1 || sysctl -p "$SYSCTL_CONF"
echo -e "${GREEN}Đã ghi cấu hình vào $SYSCTL_CONF:${NC}"
echo "  vm.swappiness = $(cat /proc/sys/vm/swappiness)"
echo "  vm.vfs_cache_pressure = $(cat /proc/sys/vm/vfs_cache_pressure)"

# ------------------------------------------------------------------------------
# 2. Mở rộng Swap lên 32GB an toàn (Zero-Downtime Safe Swap Migration)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}=== [3/4] Mở rộng bộ nhớ Swap lên 32GB trên NVMe SSD ===${NC}"
NEW_SWAP="/swap32g.img"
OLD_SWAP="/swap.img"

FREE_SPACE_GB=$(df --output=avail -BG / | tail -n 1 | tr -d ' G')
if [ "$FREE_SPACE_GB" -lt 40 ]; then
  echo -e "${RED}Cảnh báo: Ổ cứng / chỉ còn ${FREE_SPACE_GB}GB trống. Cần ít nhất 40GB để tạo swap mới an toàn.${NC}"
  exit 1
fi

echo "Dung lượng ổ NVMe còn trống: ${FREE_SPACE_GB}GB. Đang tạo file swap mới 32GB tại $NEW_SWAP..."

# Sử dụng fallocate hoặc dd
if ! fallocate -l 32G "$NEW_SWAP" 2>/dev/null; then
  echo "fallocate không được hỗ trợ, chuyển sang dd..."
  dd if=/dev/zero of="$NEW_SWAP" bs=1M count=32768 status=progress
fi

chmod 600 "$NEW_SWAP"
mkswap "$NEW_SWAP"

echo "Kích hoạt swap mới $NEW_SWAP với ưu tiên cao..."
swapon -p 10 "$NEW_SWAP"

if [ -f "$OLD_SWAP" ] && swapon --show | grep -q "$OLD_SWAP"; then
  echo "Đang tắt swap cũ $OLD_SWAP (Dữ liệu cũ sẽ di chuyển an toàn sang $NEW_SWAP mà không gây OOM)..."
  swapoff "$OLD_SWAP"
  rm -f "$OLD_SWAP"
fi

# Cập nhật /etc/fstab để tự động kích hoạt sau khi reboot
if grep -q "$OLD_SWAP" /etc/fstab; then
  sed -i "s|$OLD_SWAP|$NEW_SWAP|g" /etc/fstab
elif ! grep -q "$NEW_SWAP" /etc/fstab; then
  echo "$NEW_SWAP none swap sw 0 0" >> /etc/fstab
fi

echo -e "${GREEN}Đã kích hoạt Swap 32GB thành công.${NC}"
swapon --show

# ------------------------------------------------------------------------------
# 3. Tắt dịch vụ OCR chạy thừa trên host
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}=== [4/4] Dọn dẹp dịch vụ OCR chạy thừa trên host (ocr_server.service) ===${NC}"
if systemctl list-unit-files | grep -q "ocr_server.service"; then
  echo "Phát hiện ocr_server.service trên host. Đang dừng và vô hiệu hóa để tránh lãng phí RAM..."
  systemctl stop ocr_server.service || true
  systemctl disable ocr_server.service || true
  echo -e "${GREEN}Đã tắt ocr_server.service thành công. Toàn bộ OCR giờ đây chuẩn hóa qua Docker worker.${NC}"
else
  echo "Không tìm thấy ocr_server.service trên host hoặc đã được tắt trước đó."
fi

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}  HOÀN TẤT TỐI ƯU HÓA HẠ TẦNG DGX SPARK CHO vLLM & RAG!         ${NC}"
echo -e "${GREEN}================================================================${NC}"
free -h
