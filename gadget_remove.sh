#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# USB HID 가젯 제거 스크립트 (롤백)
# 용도: 가젯 설정을 완전히 제거하고 /dev/hidg0, hidg1 삭제
# 실행: sudo bash gadget_remove.sh
# ═══════════════════════════════════════════════════════════════════════════

set -e

echo "USB HID 가젯 제거 중..."

GADGET_PATH="/sys/kernel/config/usb_gadget/g1"

if [ ! -d "$GADGET_PATH" ]; then
    echo "가젯이 설정되어 있지 않습니다. 이미 제거된 상태."
    exit 0
fi

# ── 1단계: UDC에서 unbind ──
echo "[1/3] UDC 언바인드..."
if [ -f "$GADGET_PATH/UDC" ]; then
    echo "" | sudo tee "$GADGET_PATH/UDC" > /dev/null
    sleep 0.5
    echo "  ✓ UDC 언바인드됨"
else
    echo "  - UDC 파일 없음 (이미 언바인드됨)"
fi

# ── 2단계: configfs에서 가젯 디렉터리 제거 ──
echo "[2/3] 가젯 디렉터리 제거..."
if [ -d "$GADGET_PATH" ]; then
    sudo rm -rf "$GADGET_PATH"
    sleep 0.5
    echo "  ✓ 가젯 디렉터리 제거됨"
else
    echo "  - 이미 제거됨"
fi

# ── 3단계: /dev/hidg* 파일 삭제 (있으면) ──
echo "[3/3] /dev/hidg* 정리..."
for dev in /dev/hidg*; do
    if [ -e "$dev" ]; then
        sudo rm -f "$dev"
        echo "  ✓ $dev 삭제"
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "✓ USB HID 가젯 제거 완료!"
echo "  configfs는 마운트된 상태로 유지됩니다."
echo "  다시 가젯을 설정하려면: sudo bash gadget_restore.sh"
echo "═══════════════════════════════════════════════════════════════════════════"
