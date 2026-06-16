#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
방법 B: 실제 스위치 1개 → HID 키 전송 전체 흐름 검증
────────────────────────────────────────────────────────
목적: 물리 버튼을 손으로 누르면
      [버튼 감지] → [HID 키 전송] → [노트북에 글자] 전체 경로가
      동작하는지 확인한다.

배선 (배선도의 스위치1 자리):
  스위치 다리 1 →  GPIO 2 (물리 3번 핀)
  스위치 다리 2 →  GND   (빵판 파란 줄)
  (택트 스위치면 대각선 마주보는 두 다리 사용)

이 테스트가 보내는 글자:
  버튼을 누를 때마다  'ㅣ' (두벌식 키 = l)  를 노트북에 전송한다.
  → 배선도상 스위치1 = 천지인 모음 ㅣ 이므로 그 키를 그대로 테스트.
  → 노트북을 한글 모드로 두면 'ㅣ' 가, 영문 모드면 'l' 이 찍힌다.

실행 전 준비:
  1) 노트북 메모장을 열고 클릭.
  2) (한글 확인용) 노트북을 한글 입력 모드로 전환해두면 'ㅣ' 가 찍힌다.

실행:  sudo python3 test_switch.py   (sudo 필수)
       Ctrl+C 로 종료.
"""

import time
import sys

# ── 설정 ──────────────────────────────────────────────────
TEST_GPIO = 2                # 스위치를 꽂은 BCM GPIO 번호 (물리 3번 핀)
HIDG_KEYBOARD = "/dev/hidg0"
KEY_PRESS_INTERVAL = 0.02

# 이 스위치가 보낼 두벌식 키 (ㅣ = l).  필요하면 다른 글자로 바꿔 테스트 가능.
TEST_QWERTY_KEY = "l"        # 'ㅣ'
TEST_LABEL = "ㅣ (두벌식 키 'l')"

HID_KEYCODES = {
    "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09,
    "g": 0x0A, "h": 0x0B, "i": 0x0C, "j": 0x0D, "k": 0x0E, "l": 0x0F,
    "m": 0x10, "n": 0x11, "o": 0x12, "p": 0x13, "q": 0x14, "r": 0x15,
    "s": 0x16, "t": 0x17, "u": 0x18, "v": 0x19, "w": 0x1A, "x": 0x1B,
    "y": 0x1C, "z": 0x1D, "space": 0x2C, "enter": 0x28,
}

# ── gpiozero 버튼 ─────────────────────────────────────────
try:
    from gpiozero import Button
except Exception as e:
    print(f"[실패] gpiozero 임포트 불가: {e}")
    sys.exit(1)

# ── HID 키보드 열기 ───────────────────────────────────────
def open_keyboard():
    try:
        return open(HIDG_KEYBOARD, "wb", buffering=0)
    except FileNotFoundError:
        print(f"[실패] {HIDG_KEYBOARD} 없음 (USB 가젯 미설정).")
        sys.exit(1)
    except PermissionError:
        print(f"[실패] 권한 없음 → 'sudo python3 test_switch.py' 로 실행.")
        sys.exit(1)
    except OSError as e:
        print(f"[실패] 열기 오류: {e}")
        sys.exit(1)


def send_key(kbd, keycode, modifier=0):
    press = bytes([modifier & 0xFF, 0x00, keycode & 0xFF, 0, 0, 0, 0, 0])
    kbd.write(press); kbd.flush()
    time.sleep(KEY_PRESS_INTERVAL)
    kbd.write(bytes(8)); kbd.flush()
    time.sleep(KEY_PRESS_INTERVAL)


def main():
    print("=" * 55)
    print(" 방법 B: 실제 스위치 → HID 키 전송 테스트")
    print("=" * 55)

    # 버튼 생성
    try:
        btn = Button(TEST_GPIO, pull_up=True, bounce_time=0.05)
        print(f"[OK] 스위치 버튼 생성 (GPIO{TEST_GPIO} / 물리 3번 핀)")
    except Exception as e:
        print(f"[실패] Button(GPIO{TEST_GPIO}) 생성 불가: {e}")
        sys.exit(1)

    kbd = open_keyboard()
    print(f"[OK] {HIDG_KEYBOARD} 열기 성공\n")

    count = {"n": 0}

    def on_press():
        count["n"] += 1
        print(f"  >>> [감지] 버튼 눌림! (총 {count['n']}회) → '{TEST_LABEL}' 전송")
        code = HID_KEYCODES[TEST_QWERTY_KEY]
        send_key(kbd, code)
        print(f"      [전송완료] HID keycode 0x{code:02x}")

    btn.when_pressed = on_press

    print("준비 완료!")
    print(f" - 노트북 메모장을 클릭해 두세요.")
    print(f" - 한글 모드면 'ㅣ', 영문 모드면 'l' 이 찍힙니다.")
    print(f" - 스위치를 눌러보세요. 누를 때마다 글자가 하나씩 전송됩니다.")
    print(f" - Ctrl+C 로 종료.\n")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        kbd.close()
        print(f"\n종료. 총 버튼 눌림: {count['n']}회")
        print("노트북 메모장에 누른 횟수만큼 글자가 찍혔다면 → 전체 흐름 성공!")


if __name__ == "__main__":
    main()