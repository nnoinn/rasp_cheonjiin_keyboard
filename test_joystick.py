#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
조이스틱 ADC 값 측정 도구
────────────────────────────────────────────────────────
조이스틱을 가만히 둔 상태(중립)에서 X, Y 축의 실제 ADC 값을 출력한다.
main.py 의 ADC_CENTER, ADC_DEADZONE 을 실측값에 맞게 보정하기 위함.

실행:  sudo python3 test_joystick.py
       Ctrl+C 로 종료.

사용법:
  1) 실행 후 조이스틱에서 손을 떼고 가만히 둔다.
  2) 출력되는 X, Y 값을 본다. (이게 '중립 중심값')
  3) 조이스틱을 상하좌우로 끝까지 밀어보며 최소/최대 범위도 확인.
"""

import time
import sys

ADC_CH_X = 0
ADC_CH_Y = 1

try:
    import spidev
except Exception as e:
    print(f"[실패] spidev 임포트 불가: {e}")
    sys.exit(1)

spi = spidev.SpiDev()
try:
    spi.open(0, 0)
    spi.max_speed_hz = 1_350_000
except Exception as e:
    print(f"[실패] SPI 열기 불가: {e}")
    sys.exit(1)


def read_adc(channel):
    r = spi.xfer2([1, (8 + channel) << 4, 0])
    return ((r[1] & 3) << 8) | r[2]


print("=" * 55)
print(" 조이스틱 ADC 값 측정 (Ctrl+C 종료)")
print("=" * 55)
print(" 1) 손 떼고 가만히 둔 값 = 중립 중심값")
print(" 2) 상하좌우 끝까지 밀어 최소/최대 범위 확인")
print("-" * 55)

# 중립 추적용 최소/최대 기록
xmin = ymin = 9999
xmax = ymax = -1

try:
    while True:
        x = read_adc(ADC_CH_X)
        y = read_adc(ADC_CH_Y)
        xmin, xmax = min(xmin, x), max(xmax, x)
        ymin, ymax = min(ymin, y), max(ymax, y)
        print(f"  X={x:4d}  Y={y:4d}   "
              f"(X범위 {xmin}~{xmax}, Y범위 {ymin}~{ymax})")
        time.sleep(0.2)
except KeyboardInterrupt:
    print("\n" + "=" * 55)
    print(" 측정 종료")
    print(f"  X 관측 범위: {xmin} ~ {xmax}")
    print(f"  Y 관측 범위: {ymin} ~ {ymax}")
    print("  → 손 떼고 가만히 뒀을 때 값이 'ADC_CENTER' 가 되어야 합니다.")
    print("=" * 55)
    spi.close()