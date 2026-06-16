#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# USB HID 가젯 복원 스크립트 (g1/ 백업 기반)
# 용도: 재부팅 후 /dev/hidg0, hidg1을 character device로 재생성
# 실행: sudo bash gadget_restore.sh
# ═══════════════════════════════════════════════════════════════════════════

set -e  # 에러 시 즉시 중단

echo "USB HID 가젯 복원 시작..."

# ── 0단계: /dev/hidg* stub 파일 정리 ──
# 재부팅 후 일반 파일(-rw-)로 남아있으면 udev가 character device를 못 만듦
echo "[0/5] stub 파일 정리..."
for dev in /dev/hidg0 /dev/hidg1; do
    if [ -e "$dev" ] && [ ! -c "$dev" ]; then
        echo "  ⚠ $dev 가 일반 파일(stub). 제거 중..."
        sudo rm -f "$dev"
        echo "  ✓ stub 제거됨"
    else
        echo "  ✓ $dev 문제 없음 (없거나 이미 character device)"
    fi
done

# ── 1단계: libcomposite 모듈 로드 ──
echo ""
echo "[1/5] libcomposite 모듈 로드 중..."
sudo modprobe libcomposite 2>/dev/null && echo "  ✓ libcomposite 로드됨" || echo "  ⚠ 이미 로드되어 있거나 실패 (계속 진행)"

# ── 2단계: configfs 마운트 ──
echo ""
echo "[2/5] configfs 마운트 확인..."
if ! grep -q "configfs" /proc/mounts; then
    echo "  - configfs 미마운트, 마운트 중..."
    sudo mount -t configfs none /sys/kernel/config/
    echo "  ✓ configfs 마운트됨"
else
    echo "  ✓ configfs 이미 마운트됨"
fi

# ── 3단계: /sys/kernel/config/usb_gadget/ 확인 & 기존 gadget 제거 ──
# configfs는 가상 파일시스템이라 rm -rf 불가. 반드시 순서대로 rmdir.
echo ""
echo "[3/5] 가젯 설정 디렉터리 준비..."
GADGET_PATH="/sys/kernel/config/usb_gadget/g1"
if [ -d "$GADGET_PATH" ]; then
    echo "  - 기존 g1 가젯 발견, 순서대로 제거 중..."
    # 1) UDC unbind (가젯 비활성화)
    if [ -f "$GADGET_PATH/UDC" ] && [ -n "$(cat $GADGET_PATH/UDC 2>/dev/null)" ]; then
        echo "" | sudo tee "$GADGET_PATH/UDC" > /dev/null 2>&1 || true
        sleep 0.5
    fi
    # 2) configs 심볼릭 링크 제거
    sudo rm -f "$GADGET_PATH/configs/c.1/hid.usb0" 2>/dev/null || true
    sudo rm -f "$GADGET_PATH/configs/c.1/hid.usb1" 2>/dev/null || true
    # 3) configs strings → configs 순으로 rmdir
    sudo rmdir "$GADGET_PATH/configs/c.1/strings/0x409" 2>/dev/null || true
    sudo rmdir "$GADGET_PATH/configs/c.1" 2>/dev/null || true
    # 4) functions rmdir
    sudo rmdir "$GADGET_PATH/functions/hid.usb0" 2>/dev/null || true
    sudo rmdir "$GADGET_PATH/functions/hid.usb1" 2>/dev/null || true
    # 5) gadget strings rmdir
    sudo rmdir "$GADGET_PATH/strings/0x409" 2>/dev/null || true
    # 6) 가젯 루트 rmdir
    sudo rmdir "$GADGET_PATH" 2>/dev/null || true
    sleep 0.3
    echo "  ✓ 기존 가젯 제거됨"
fi

# ── 4단계: 새 가젯 생성 ──
echo ""
echo "[4/5] 새 USB HID 가젯 생성 중..."

# 가젯 루트
sudo mkdir -p "$GADGET_PATH"
cd "$GADGET_PATH"

# 기본 속성 설정
echo "0x1d6b" | sudo tee idVendor > /dev/null
echo "0x0104" | sudo tee idProduct > /dev/null
echo "0x0100" | sudo tee bcdDevice > /dev/null
echo "0x0200" | sudo tee bcdUSB > /dev/null

# 문자열 (manufacturer, product, serialnumber)
sudo mkdir -p strings/0x409
echo "MyCustom" | sudo tee strings/0x409/manufacturer > /dev/null
echo "Chunjiin Pad" | sudo tee strings/0x409/product > /dev/null
echo "7777777" | sudo tee strings/0x409/serialnumber > /dev/null

echo "  ✓ 가젯 루트 속성 설정됨"

# ── 4-1: HID 함수 생성 (키보드 usb0) ──
echo "  - HID 키보드 함수(usb0) 생성..."
sudo mkdir -p functions/hid.usb0
echo "1" | sudo tee functions/hid.usb0/protocol > /dev/null
echo "1" | sudo tee functions/hid.usb0/subclass > /dev/null
echo "8" | sudo tee functions/hid.usb0/report_length > /dev/null

# 키보드 HID 리포트 디스크립터 (표준 부트 키보드, 63바이트)
# python3 hex 방식 사용 — bash printf는 null 바이트(\x00)를 command substitution에서 잘라냄
python3 -c "import sys; sys.stdout.buffer.write(bytes.fromhex('05010906a101050719e029e71500250175019508810295017508810395057501050819012905910295017503910395067508150025650507190029658100c0'))" | sudo tee functions/hid.usb0/report_desc > /dev/null
echo "  ✓ 키보드 함수 생성됨"

# ── 4-2: HID 함수 생성 (마우스 usb1) ──
echo "  - HID 마우스 함수(usb1) 생성..."
sudo mkdir -p functions/hid.usb1
echo "1" | sudo tee functions/hid.usb1/protocol > /dev/null
echo "1" | sudo tee functions/hid.usb1/subclass > /dev/null
echo "4" | sudo tee functions/hid.usb1/report_length > /dev/null

# 마우스 HID 리포트 디스크립터 (표준 마우스, 52바이트)
# python3 hex 방식 사용 — bash printf는 null 바이트(\x00)를 command substitution에서 잘라냄
python3 -c "import sys; sys.stdout.buffer.write(bytes.fromhex('05010902a1010901a1000509190129031500250195037501810295017505810305010930093109381581257f750895038106c0c0'))" | sudo tee functions/hid.usb1/report_desc > /dev/null
echo "  ✓ 마우스 함수 생성됨"

# ── 4-3: 설정(config) 생성 ──
echo "  - 설정(config) 생성..."
sudo mkdir -p configs/c.1/strings/0x409
echo "Configuration 1" | sudo tee configs/c.1/strings/0x409/configuration > /dev/null
echo "500" | sudo tee configs/c.1/MaxPower > /dev/null

# 함수를 config에 링크
sudo ln -s functions/hid.usb0 configs/c.1/hid.usb0
sudo ln -s functions/hid.usb1 configs/c.1/hid.usb1
echo "  ✓ 설정 생성 및 함수 연결됨"

# ── 5단계: UDC에 바인드 (가젯 활성화) ──
echo ""
echo "[5/5] UDC 바인드 (가젯 활성화)..."
UDC="fe980000.usb"
echo "$UDC" | sudo tee UDC > /dev/null
sleep 1
echo "  ✓ UDC '$UDC' 바인드됨"

# ── 5.5단계: /dev/hidg* character device 확인 및 mknod fallback ──
# udev가 느리거나 stub 잔재로 자동 생성 실패 시 수동 생성
sleep 1
echo "  - /dev/hidg* character device 확인..."
for i in 0 1; do
    dev="/dev/hidg$i"
    if [ ! -c "$dev" ]; then
        echo "  ⚠ $dev character device 없음. mknod으로 수동 생성..."
        major=$(cut -d: -f1 /sys/class/hidg/hidg$i/dev)
        minor=$(cut -d: -f2 /sys/class/hidg/hidg$i/dev)
        sudo mknod "$dev" c "$major" "$minor"
        sudo chmod 660 "$dev"
        echo "  ✓ $dev 수동 생성됨 (major=$major, minor=$minor)"
    else
        echo "  ✓ $dev 정상 (character device)"
    fi
done

# ── 검증 ──
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "✓ USB HID 가젯 복원 완료!"
echo ""
echo "확인:"
ls -l /dev/hidg0 /dev/hidg1 2>&1
echo ""
echo "다음 단계: sudo python3 main.py"
echo "═══════════════════════════════════════════════════════════════════════════"
