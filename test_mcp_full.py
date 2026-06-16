#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP3008 SPI 종합 진단 도구
────────────────────────────────────────────────────────
CS선이 CE0(물리24/GPIO8)인지 CE1(물리26/GPIO7)인지 모를 때,
양쪽 다 열어보고 8개 채널을 전부 읽어 MCP 통신 여부를 판정한다.

실행:  sudo python3 test_mcp_full.py
       Ctrl+C 로 종료.

판정:
  - 어떤 device 에서든 0,1023 같은 '의미있는 값'이 나오면 MCP 통신 성공.
  - 모든 device, 모든 채널이 0(또는 1023 고정)이면 통신 실패 → 배선/전원 문제.
"""

import time
import sys

try:
    import spidev
except Exception as e:
    print(f"[실패] spidev 임포트 불가: {e}")
    sys.exit(1)


def read_adc(spi, channel):
    r = spi.xfer2([1, (8 + channel) << 4, 0])
    return ((r[1] & 3) << 8) | r[2]


def try_device(bus, device):
    """해당 (bus, device)=CE 핀으로 열어 8채널 읽기 시도."""
    spi = spidev.SpiDev()
    try:
        spi.open(bus, device)
        spi.max_speed_hz = 1_350_000
    except Exception as e:
        print(f"  spi.open({bus},{device}) 실패: {e}")
        return None
    vals = []
    for ch in range(8):
        try:
            vals.append(read_adc(spi, ch))
        except Exception as e:
            vals.append(f"ERR")
    spi.close()
    return vals


print("=" * 60)
print(" MCP3008 SPI 종합 진단 (Ctrl+C 종료)")
print("=" * 60)
print(" CE0 = 물리24핀(GPIO8),  CE1 = 물리26핀(GPIO7)")
print(" 조이스틱은 CH0(X), CH1(Y) 에 연결되어 있어야 함")
print(" 값이 모두 0 또는 1023 고정 = 통신 실패 / 다양한 값 = 통신 성공")
print("-" * 60)

try:
    while True:
        ce0 = try_device(0, 0)   # /dev/spidev0.0
        ce1 = try_device(0, 1)   # /dev/spidev0.1
        print(f"  CE0(0.0): {ce0}")
        print(f"  CE1(0.1): {ce1}")
        print("  " + "-" * 50)
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\n진단 종료.")
    print("  → CE0 또는 CE1 중 한쪽에서 CH0,CH1 값이 조이스틱 따라 변하면")
    print("     그 device 번호로 main.py 의 spi.open 을 맞추면 됩니다.")