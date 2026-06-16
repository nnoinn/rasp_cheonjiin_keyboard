#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
조이스틱 버튼(GPIO 23 / 물리 16번) 단독 진단 스크립트
────────────────────────────────────────────────────────
목적: main.py 와 무관하게, GPIO 23 버튼 신호가 라즈베리파이로
      실제 들어오는지 '눈으로' 확인한다.

실행:  sudo python3 test_button.py
       (Ctrl+C 로 종료)

배선 전제(현재 구성):
  조이스틱 SW  →  GPIO 23 (물리 16번 핀)  직결
  조이스틱 GND →  빵판 GND (파란 줄)
  → pull_up=True : 평소 HIGH(안 눌림), 누르면 GND로 떨어져 LOW(눌림)
"""

import sys
import time

print("=" * 55)
print(" GPIO 23 조이스틱 버튼 진단 시작")
print("=" * 55)

# ── 1) gpiozero 임포트 가능 여부부터 확인 ──────────────────
try:
    from gpiozero import Button
    print("[OK] gpiozero 임포트 성공")
except Exception as e:
    print(f"[실패] gpiozero 임포트 불가: {e}")
    print("      → sudo apt install python3-gpiozero  로 설치 필요")
    sys.exit(1)

# ── 2) 버튼 객체 생성 (실패하면 그 이유가 핵심 단서) ──────
try:
    btn = Button(23, pull_up=True, bounce_time=0.05)
    print("[OK] Button(23, pull_up=True) 생성 성공")
except Exception as e:
    print(f"[실패] Button(23) 생성 불가: {e}")
    print("      → 핀 팩토리 문제일 수 있음. 아래를 시도:")
    print("        pip install lgpio")
    print("        또는  export GPIOZERO_PIN_FACTORY=lgpio")
    sys.exit(1)

# ── 3) 콜백 방식과 폴링 방식 둘 다 테스트 ─────────────────
press_count = {"n": 0}

def on_press():
    press_count["n"] += 1
    print(f"  >>> [콜백] 버튼 눌림 감지!  (총 {press_count['n']}회)")

def on_release():
    print("  <<< [콜백] 버튼 떼짐")

btn.when_pressed = on_press
btn.when_released = on_release

print("\n준비 완료. 이제 버튼을 눌러보세요.")
print("  - 누르면 '버튼 눌림 감지', 떼면 '버튼 떼짐' 이 떠야 정상입니다.")
print("  - 콜백 로그와 폴링 상태값이 함께 출력됩니다.")
print("  - Ctrl+C 로 종료\n")

# ── 4) 메인 루프: 0.2초마다 현재 핀 상태(is_pressed)도 출력 ──
try:
    last_state = None
    while True:
        state = btn.is_pressed   # pull_up 보정됨: 누르면 True
        if state != last_state:
            # 상태가 바뀔 때만 출력(폴링 방식 확인용)
            print(f"      [폴링] is_pressed = {state}")
            last_state = state
        time.sleep(0.05)
except KeyboardInterrupt:
    print(f"\n종료. 총 버튼 눌림 횟수: {press_count['n']}회")