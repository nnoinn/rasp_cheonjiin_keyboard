#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한글 HID 전송 검증 테스트 (두벌식 조합)
────────────────────────────────────────────────────────
목적: 라즈베리파이가 한글 글자를 두벌식 자판 키로 분해해 전송하면,
      노트북의 한글 IME 가 실제로 '가, 나, 값, 꽃' 등으로 조합하는지 확인.

★★★ 가장 중요한 준비 ★★★
  노트북을 '한글 입력 모드'로 바꿔두어야 한다!
  (메모장을 클릭한 뒤, 노트북에서 한/영 키를 눌러 한글 상태로 전환)
  → 영문 상태로 두면 '가' 가 아니라 'rk' 처럼 알파벳이 찍힌다.

실행 전 준비:
  1) 노트북에서 메모장(또는 한글 입력 가능한 창)을 연다.
  2) 그 창을 클릭한다.
  3) 노트북에서 한/영 키를 눌러 '한글 입력 모드'로 만든다.
  4) 7초 카운트다운 동안 위 1~3을 완료해 두면 된다.

실행:  sudo python3 test_hangul.py   (sudo 필수)

전송 단어: 가  나  다  →  한  글  →  값  꽃
  '가'  = ㄱ(r) ㅏ(k)
  '나'  = ㄴ(s) ㅏ(k)
  '다'  = ㄷ(e) ㅏ(k)
  '한'  = ㅎ(g) ㅏ(k) ㄴ(s)
  '글'  = ㄱ(r) ㅡ(m) ㄹ(f)
  '값'  = ㄱ(r) ㅏ(k) ㅂ(q) ㅅ(t)   ← 겹받침 ㅄ
  '꽃'  = ㄲ(R=Shift+r) ㅗ(h) ㅊ(c)  ← 쌍자음+받침
"""

import time
import sys

HIDG_KEYBOARD = "/dev/hidg0"
KEY_PRESS_INTERVAL = 0.03   # 한글은 IME 조합 시간이 필요해 약간 넉넉히

# ── 표준 HID 키코드 ───────────────────────────────────────
HID_KEYCODES = {
    "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09,
    "g": 0x0A, "h": 0x0B, "i": 0x0C, "j": 0x0D, "k": 0x0E, "l": 0x0F,
    "m": 0x10, "n": 0x11, "o": 0x12, "p": 0x13, "q": 0x14, "r": 0x15,
    "s": 0x16, "t": 0x17, "u": 0x18, "v": 0x19, "w": 0x1A, "x": 0x1B,
    "y": 0x1C, "z": 0x1D, "space": 0x2C, "enter": 0x28,
}
SHIFT_MOD = 0x02   # 왼쪽 Shift modifier 비트

# ── 한글 자모 → 두벌식 QWERTY 키 (소문자=평음, 대문자=Shift) ──
JAMO_TO_QWERTY = {
    "ㄱ": "r",  "ㄲ": "R",  "ㄴ": "s",  "ㄷ": "e",  "ㄸ": "E",
    "ㄹ": "f",  "ㅁ": "a",  "ㅂ": "q",  "ㅃ": "Q",  "ㅅ": "t",
    "ㅆ": "T",  "ㅇ": "d",  "ㅈ": "w",  "ㅉ": "W",  "ㅊ": "c",
    "ㅋ": "z",  "ㅌ": "x",  "ㅍ": "v",  "ㅎ": "g",
    "ㅏ": "k",  "ㅐ": "o",  "ㅑ": "i",  "ㅒ": "O",  "ㅓ": "j",
    "ㅔ": "p",  "ㅕ": "u",  "ㅖ": "P",  "ㅗ": "h",  "ㅛ": "y",
    "ㅜ": "n",  "ㅠ": "b",  "ㅡ": "m",  "ㅣ": "l",
    "ㅘ": "hk", "ㅙ": "ho", "ㅚ": "hl", "ㅝ": "nj", "ㅞ": "np",
    "ㅟ": "nl", "ㅢ": "ml",
    "ㄳ": "rt", "ㄵ": "sw", "ㄶ": "sg", "ㄺ": "fr", "ㄻ": "fa",
    "ㄼ": "fq", "ㄽ": "ft", "ㄾ": "fx", "ㄿ": "fv", "ㅀ": "fg",
    "ㅄ": "qt",
}

# 유니코드 한글 분해용
CHOSUNG = ['ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ','ㅆ','ㅇ',
           'ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']
JUNGSUNG = ['ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ','ㅘ','ㅙ','ㅚ',
            'ㅛ','ㅜ','ㅝ','ㅞ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ']
JONGSUNG = ['','ㄱ','ㄲ','ㄳ','ㄴ','ㄵ','ㄶ','ㄷ','ㄹ','ㄺ','ㄻ','ㄼ','ㄽ',
            'ㄾ','ㄿ','ㅀ','ㅁ','ㅂ','ㅄ','ㅅ','ㅆ','ㅇ','ㅈ','ㅊ','ㅋ',
            'ㅌ','ㅍ','ㅎ']
HANGUL_BASE = 0xAC00


def decompose(ch):
    code = ord(ch)
    if not (HANGUL_BASE <= code <= HANGUL_BASE + 11171):
        return None
    idx = code - HANGUL_BASE
    cho = idx // (21 * 28)
    jung = (idx % (21 * 28)) // 28
    jong = idx % 28
    return CHOSUNG[cho], JUNGSUNG[jung], JONGSUNG[jong]


def hangul_to_keys(ch):
    """한글 1글자 → 두벌식 키 시퀀스 문자열. 비한글은 그대로."""
    parts = decompose(ch)
    if parts is None:
        return ch
    seq = ""
    for jamo in parts:
        if jamo:
            seq += JAMO_TO_QWERTY.get(jamo, "")
    return seq


def open_keyboard():
    try:
        return open(HIDG_KEYBOARD, "wb", buffering=0)
    except FileNotFoundError:
        print(f"[실패] {HIDG_KEYBOARD} 없음 (USB 가젯 미설정).")
        sys.exit(1)
    except PermissionError:
        print(f"[실패] 권한 없음 → 'sudo python3 test_hangul.py' 로 실행.")
        sys.exit(1)
    except OSError as e:
        print(f"[실패] 열기 오류: {e}")
        sys.exit(1)


def send_key(kbd, keycode, modifier=0):
    press = bytes([modifier & 0xFF, 0x00, keycode & 0xFF, 0, 0, 0, 0, 0])
    kbd.write(press); kbd.flush()
    time.sleep(KEY_PRESS_INTERVAL)
    kbd.write(bytes(8)); kbd.flush()   # release
    time.sleep(KEY_PRESS_INTERVAL)


def send_qwerty_char(kbd, ch):
    """두벌식 키 문자 1개 전송. 대문자면 Shift 적용(쌍자음)."""
    mod = 0
    c = ch
    if ch.isupper():
        mod = SHIFT_MOD
        c = ch.lower()
    code = HID_KEYCODES.get(c)
    if code is None:
        return
    send_key(kbd, code, mod)


def send_hangul(kbd, word):
    """한글 단어를 글자별로 분해 전송."""
    for ch in word:
        keys = hangul_to_keys(ch)
        shown = " ".join(keys) if keys else ch
        print(f"   '{ch}'  →  {shown}")
        for k in keys:
            send_qwerty_char(kbd, k)


def main():
    print("=" * 55)
    print(" 한글 HID 전송 검증 테스트 (두벌식 조합)")
    print("=" * 55)

    kbd = open_keyboard()
    print(f"[OK] {HIDG_KEYBOARD} 열기 성공\n")

    print("★★★ 매우 중요 ★★★")
    print(" 노트북을 '한글 입력 모드'로 바꿔두세요!")
    print("  1) 노트북 메모장 클릭")
    print("  2) 노트북에서 한/영 키를 눌러 한글 상태로 전환")
    print("  → 영문 상태면 '가' 가 아니라 'rk' 로 찍힙니다.\n")
    for i in range(7, 0, -1):
        print(f"  {i}초 후 시작... (지금 한글 모드로 전환!)")
        time.sleep(1)
    print()

    # 한 단어씩 전송하고, 사이에 Space 로 구분
    words = ["가", "나", "다", "한", "글", "값", "꽃"]
    for w in words:
        print(f">>> '{w}' 전송")
        send_hangul(kbd, w)
        send_key(kbd, HID_KEYCODES["space"])   # 글자 구분용 띄어쓰기

    kbd.close()
    print("\n" + "=" * 55)
    print(" 완료! 노트북에 이렇게 찍혔는지 확인:")
    print("     가 나 다 한 글 값 꽃")
    print("-" * 55)
    print(" [정상]  위처럼 한글로 조합됨 → 한글 전송 성공!")
    print(" [rk sk..] 알파벳으로 찍힘   → 노트북이 영문 모드였음.")
    print("                              한글 모드로 바꾸고 재시도.")
    print(" [가나다 가 아니라 깨짐]    → IME 조합 타이밍 문제.")
    print("                              알려주시면 간격을 조정합니다.")
    print("=" * 55)


if __name__ == "__main__":
    main()