#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
16키 핀 스캐너 — 스위치 하나로 모든 핀을 순서 없이 확인
────────────────────────────────────────────────────────
목적: 스위치 1개를 16개 GPIO 핀 어디에 꽂든,
      어느 핀이 눌렸는지 자동 감지하고
      '배선도상 몇 번 스위치 / 무슨 기능 / 두벌식 키' 인지 알려준다.
      동시에 그 키를 노트북으로 HID 전송한다.

장점: 핀을 옮길 때마다 코드를 고칠 필요 없이,
      스위치를 다른 핀에 꽂고 누르기만 하면 된다.

배선:
  스위치 다리 1 → (확인하려는 GPIO 핀)
  스위치 다리 2 → GND (빵판 파란 줄)

실행:  sudo python3 test_scan_all.py   (sudo 필수)
       Ctrl+C 로 종료.

노트북 준비:
  메모장 열고 클릭. 한글 모드면 한글이, 영문 모드면 알파벳이 찍힌다.
"""

import time
import sys

HIDG_KEYBOARD = "/dev/hidg0"
KEY_PRESS_INTERVAL = 0.02

# ── 배선도: 스위치번호 → (GPIO, 기능설명, 전송할 두벌식키 또는 특수동작) ──
#   key_action 종류:
#     ("qwerty", "r")  : 두벌식 키 'r' 전송 (예: ㄱ)
#     ("multi", "rz")  : 여러 키(토글 후보) — 첫 키만 전송하되 후보 안내
#     ("special", "Backspace") : 특수 기능(엔터/백스페이스/스페이스 등)
#     ("mode", "한/영") : 모드 전환류 (실제 전송 없음, 안내만)
SWITCH_MAP = {
    2:  (1,  "ㅣ / a,b,c",          ("qwerty", "l")),
    3:  (2,  "ㆍ(아래아) / d,e,f",  ("special", "(천지인 모음 ㆍ, 단독키 없음)")),
    4:  (3,  "ㅡ / g,h,i",          ("qwerty", "m")),
    17: (4,  "Backspace",           ("special", "Backspace")),
    27: (5,  "ㄱ,ㅋ / j,k,l",       ("qwerty", "r")),
    22: (6,  "ㄴ,ㄹ / m,n,o",       ("qwerty", "s")),
    5:  (7,  "ㄷ,ㅌ / p,q,r",       ("qwerty", "e")),
    6:  (8,  "Enter",               ("special", "Enter")),
    13: (9,  "ㅂ,ㅍ / s,t,u",       ("qwerty", "q")),
    19: (10, "ㅅ,ㅎ / v,w",         ("qwerty", "t")),
    26: (11, "ㅈ,ㅊ / x,y,z",       ("qwerty", "w")),
    14: (12, "한/영 전환",          ("mode", "한/영 전환")),
    15: (13, "Shift(쌍자음)",       ("mode", "Shift")),
    18: (14, "ㅇ,ㅁ / 특수문자",    ("qwerty", "d")),
    24: (15, "Space",               ("special", "Space")),
    25: (16, "커스텀 모드 전환",    ("mode", "커스텀 모드")),
}

# 시리얼 콘솔 점유로 충돌 가능성이 있는 핀 안내용
UART_PINS = {14, 15}

HID_KEYCODES = {
    "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09,
    "g": 0x0A, "h": 0x0B, "i": 0x0C, "j": 0x0D, "k": 0x0E, "l": 0x0F,
    "m": 0x10, "n": 0x11, "o": 0x12, "p": 0x13, "q": 0x14, "r": 0x15,
    "s": 0x16, "t": 0x17, "u": 0x18, "v": 0x19, "w": 0x1A, "x": 0x1B,
    "y": 0x1C, "z": 0x1D, "space": 0x2C, "enter": 0x28, "backspace": 0x2A,
}
SPECIAL_KEYCODE = {
    "Enter": "enter", "Backspace": "backspace", "Space": "space",
}

try:
    from gpiozero import Button
except Exception as e:
    print(f"[실패] gpiozero 임포트 불가: {e}")
    sys.exit(1)


def open_keyboard():
    try:
        return open(HIDG_KEYBOARD, "wb", buffering=0)
    except FileNotFoundError:
        print(f"[실패] {HIDG_KEYBOARD} 없음 (USB 가젯 미설정).")
        sys.exit(1)
    except PermissionError:
        print("[실패] 권한 없음 → 'sudo python3 test_scan_all.py' 로 실행.")
        sys.exit(1)
    except OSError as e:
        print(f"[실패] 열기 오류: {e}")
        sys.exit(1)


def send_key(kbd, keycode, modifier=0):
    kbd.write(bytes([modifier & 0xFF, 0, keycode & 0xFF, 0, 0, 0, 0, 0]))
    kbd.flush()
    time.sleep(KEY_PRESS_INTERVAL)
    kbd.write(bytes(8)); kbd.flush()
    time.sleep(KEY_PRESS_INTERVAL)


def make_handler(kbd, gpio, sw_no, desc, action):
    kind, payload = action

    def handler():
        print("─" * 50)
        print(f"  >>> [감지] GPIO{gpio} 눌림!")
        print(f"      배선도: 스위치 {sw_no}번  |  기능: {desc}")
        if kind == "qwerty":
            code = HID_KEYCODES.get(payload)
            if code:
                send_key(kbd, code)
                print(f"      [전송] 두벌식 키 '{payload}' (0x{code:02x})")
                print(f"             → 노트북 한글모드면 해당 자모가 찍힘")
        elif kind == "special":
            kc_name = SPECIAL_KEYCODE.get(payload)
            if kc_name:
                send_key(kbd, HID_KEYCODES[kc_name])
                print(f"      [전송] 특수키 {payload}")
            else:
                print(f"      [안내] {payload} — 단독 전송 키 없음(엔진에서 조합)")
        elif kind == "mode":
            print(f"      [안내] {payload} 키 — 실제 펌웨어(main.py)에서 모드 전환")
            print(f"             이 스캐너에선 전송 없이 감지만 확인")
        print(f"      → 핀 위치/기능이 위 내용과 맞으면 정상!")

    return handler


def main():
    print("=" * 55)
    print(" 16키 핀 스캐너 (스위치 하나로 전체 확인)")
    print("=" * 55)

    kbd = open_keyboard()
    print(f"[OK] {HIDG_KEYBOARD} 열기 성공")

    # 16개 핀 전부에 버튼 객체 생성(개별 try)
    buttons = {}
    ok, fail = [], []
    for gpio, (sw_no, desc, action) in SWITCH_MAP.items():
        try:
            b = Button(gpio, pull_up=True, bounce_time=0.05)
            b.when_pressed = make_handler(kbd, gpio, sw_no, desc, action)
            buttons[gpio] = b
            ok.append(gpio)
        except Exception as e:
            fail.append((gpio, sw_no, str(e)))

    print(f"[OK] 핀 감지 대기 중: {len(ok)}개 핀")
    if fail:
        print(f"[INFO] {len(fail)}개 핀은 객체 생성 실패(사용중일 수 있음):")
        for gpio, sw_no, msg in fail:
            warn = " ← UART 점유 가능" if gpio in UART_PINS else ""
            print(f"        - GPIO{gpio} (스위치{sw_no}){warn}: {msg.splitlines()[0]}")
        print("        (스위치12=GPIO14, 스위치13=GPIO15 는 시리얼콘솔과 충돌할 수 있음)")

    print()
    print("사용법:")
    print(" 1) 노트북 메모장 클릭 (한글 모드 권장)")
    print(" 2) 스위치를 아무 GPIO 핀에 꽂고 누른다")
    print(" 3) 터미널이 '몇 번 스위치인지' 알려주고, 노트북에 글자 전송")
    print(" 4) 다른 핀으로 옮겨 꽂고 반복 (코드 수정 불필요)")
    print(" - Ctrl+C 로 종료\n")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        kbd.close()
        print("\n종료. 수고했어요!")


if __name__ == "__main__":
    main()