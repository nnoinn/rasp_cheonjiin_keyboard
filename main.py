#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
 라즈베리파이 4 — 16키 천지인 키보드  USB HID 가젯 펌웨어  (main.py)
═══════════════════════════════════════════════════════════════════════════
 [통합 메인] 이 파일이 프로젝트의 단일 실행 진입점이다.
   실행:  sudo python3 main.py
   (이전의 pyautogui 출력 버전은 폐기됨. 출력은 전부 USB HID 가젯.)

 라즈베리파이를 C타입으로 타겟 PC/스마트폰에 연결해 '외장 USB 키보드+마우스'로
 동작시킨다. 소프트웨어 타이핑(pyautogui/xclip) 전면 폐기 →
 USB HID 가젯 장치 파일에 raw HID 리포트 바이트를 직접 기록한다.
   - /dev/hidg0 : 키보드 (8바이트 리포트)
   - /dev/hidg1 : 마우스  (4바이트 리포트)

 [전제]
   - dwc2 / libcomposite 가젯 모드 설정 완료, /dev/hidg0, /dev/hidg1 존재.
   - 키보드 HID 디스크립터: 표준 부트 키보드(8바이트)
       byte0 = modifier 비트마스크
       byte1 = reserved(0)
       byte2~7 = 최대 6키 동시(keycode), 본 펌웨어는 1키씩 사용
   - 마우스 HID 디스크립터: 4바이트
       byte0 = 버튼 비트(bit0=좌, bit1=우, bit2=중간)
       byte1 = X 이동(int8, -127~127)
       byte2 = Y 이동(int8)
       byte3 = 휠(int8)

 [유지]
   - 천지인 엔진 v2 알고리즘, 4x4 핀 맵, 조이스틱 핀 규칙 100% 유지.
   - 출력단만 HID 가젯 전용으로 교체.

 [한글 전송 원리]
   천지인 엔진이 완성한 한글('가')을 타겟 PC의 '두벌식' IME 가 조합하도록,
   완성형을 초/중/종성으로 분해 → 각 자모를 두벌식 자판(QWERTY) 키로 역매핑 →
   순서대로 키 신호 전송. (예: '가' → ㄱ(r) → ㅏ(k))
═══════════════════════════════════════════════════════════════════════════
"""

import json
import os
import socket
import sys
import threading
import time
import signal
from http.server import ThreadingHTTPServer
from web_setter import SetterHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from cheonjiin_engine_v2 import (
        CheonjiinEngine, CHOSUNG, JUNGSUNG, JONGSUNG, HANGUL_BASE
    )
except ImportError:
    from cheonjiin_engine import (  # type: ignore
        CheonjiinEngine, CHOSUNG, JUNGSUNG, JONGSUNG, HANGUL_BASE
    )


# ═══════════════════════════════════════════════════════════════════════════
# 0. 하드웨어 핀 맵 / 상수  (실제 배선도 기준 — BCM GPIO 번호)
# ═══════════════════════════════════════════════════════════════════════════
#  아래 KEY_GPIO_MAP 의 키(1~16)는 '물리 스위치 번호'이며, 각 값은 그 스위치가
#  연결된 BCM GPIO 번호다. 배선도 표를 그대로 옮긴 것.
#
#   스위치 | 기능(한/영)          | GPIO | 물리핀
#   ------ | -------------------- | ---- | -----
#     1    | ㅣ / a,b,c           |  2   |  3
#     2    | ㆍ / d,e,f           |  3   |  5
#     3    | ㅡ / g,h,i           |  4   |  7
#     4    | Backspace            | 17   | 11
#     5    | ㄱ,ㅋ / j,k,l        | 27   | 13
#     6    | ㄴ,ㄹ / m,n,o        | 22   | 15
#     7    | ㄷ,ㅌ / p,q,r        |  5   | 29
#     8    | Enter                |  6   | 31
#     9    | ㅂ,ㅍ / s,t,u        | 13   | 33
#    10    | ㅅ,ㅎ / v,w          | 19   | 35
#    11    | ㅈ,ㅊ / x,y,z        | 26   | 37
#    12    | 한/영 전환           | 14   |  8
#    13    | Shift (쌍자음)       | 15   | 10
#    14    | ㅇ,ㅁ / 특수문자     | 18   | 12
#    15    | Space                | 24   | 18
#    16    | 커스텀 모드 전환     | 25   | 22
#   조이스틱 SW                   | 23   | 16
KEY_GPIO_MAP = {
    1: 2,   2: 3,   3: 4,   4: 17,
    5: 27,  6: 22,  7: 5,   8: 6,
    9: 13,  10: 19, 11: 26, 12: 14,
    13: 15, 14: 18, 15: 24, 16: 25,
}
SHIFT_GPIO = 15            # 스위치13 = Shift(쌍자음)
JOYSTICK_BTN_GPIO = 23     # 조이스틱 SW (물리 16번)

HANGUL_TOGGLE_KEY_ID = 12  # 스위치12 = 한/영 전환
FIXED_KEY_ID = 16          # 스위치16 = 커스텀 모드 전환

ADC_CH_X = 0
ADC_CH_Y = 1
ADC_MAX = 1023
ADC_CENTER = 512
ADC_DEADZONE = 60
MOUSE_SPEED = 10            # HID X/Y는 int8(-127~127). 틱당 최대 이동량.

LOOP_DELAY = 0.01
RIGHT_CLICK_HOLD = 0.5

# 한/영 전환 HID 방식: 실기로 동작 확인 후 이 상수 한 곳만 바꾸면 됨
# (keycode, modifier) 튜플로 hid.send_key(*HANGUL_HID) 로 전송
HANGUL_HID_CANDIDATES = {
    'RALT':  (0,    0x40),   # Right Alt modifier  ← 현재 시도 중
    'LANG1': (0x90, 0),      # LANG1 keycode (0x90) — 일부 노트북에서 미인식
    'LANG2': (0x91, 0),      # LANG2(한자키) keycode (0x91)
    'RCTRL': (0,    0x10),   # Right Ctrl modifier
}
HANGUL_HID = HANGUL_HID_CANDIDATES['RALT']   # ← 동작하는 방식으로 교체

AUTO_CONFIRM_TIMEOUT  = 1.0   # 무입력 후 조합 자동확정 (초)
BS_HOLD_THRESHOLD    = 1.5    # backspace 꾹 누름 → 연속삭제 시작 (초)
BS_REPEAT_INTERVAL   = 0.08   # 연속삭제 간격 (초)
CONFIG_CHECK_INTERVAL = 1.0   # config.json mtime 체크 간격 (초)

# 마우스 클릭 리포트 유지 시간(초).
# 키보드용 KEY_PRESS_INTERVAL(8ms)보다 길게 잡아야 타겟 OS가 버튼 눌림을
# 확실히 인식한다. 또한 이동 폴링(LOOP_DELAY=10ms)이 버튼 0 리포트로
# press 를 덮어쓰지 않도록, 클릭 처리 동안에는 이동 송신을 일시 보류한다.
MOUSE_CLICK_PRESS_MS = 0.04    # 40ms 동안 버튼 눌림 유지
MOUSE_CLICK_RELEASE_MS = 0.02  # 20ms 동안 릴리즈 상태 안정화

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
# FIXED_KEY_ID, HANGUL_TOGGLE_KEY_ID 는 위 핀맵 섹션에서 이미 정의됨

# HID 장치 파일
HIDG_KEYBOARD = "/dev/hidg0"
HIDG_MOUSE = "/dev/hidg1"

# 키 신호 사이 간격(타겟 PC IME가 인식할 시간). 너무 짧으면 누락될 수 있음.
KEY_PRESS_INTERVAL = 0.008


# ═══════════════════════════════════════════════════════════════════════════
# 1. 표준 HID 키코드 테이블 (USB HID Usage Tables, Keyboard/Keypad Page 0x07)
#    값은 keycode(byte2~7에 들어갈 값). modifier는 별도 비트마스크.
# ═══════════════════════════════════════════════════════════════════════════
HID_KEYCODES = {
    # 알파벳
    "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09,
    "g": 0x0A, "h": 0x0B, "i": 0x0C, "j": 0x0D, "k": 0x0E, "l": 0x0F,
    "m": 0x10, "n": 0x11, "o": 0x12, "p": 0x13, "q": 0x14, "r": 0x15,
    "s": 0x16, "t": 0x17, "u": 0x18, "v": 0x19, "w": 0x1A, "x": 0x1B,
    "y": 0x1C, "z": 0x1D,
    # 숫자(상단)
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,
    # 제어/공백
    "enter": 0x28, "return": 0x28, "esc": 0x29, "escape": 0x29,
    "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
    # 기호
    "minus": 0x2D, "-": 0x2D, "equal": 0x2E, "=": 0x2E,
    "lbracket": 0x2F, "[": 0x2F, "rbracket": 0x30, "]": 0x30,
    "backslash": 0x31, "\\": 0x31, "semicolon": 0x33, ";": 0x33,
    "quote": 0x34, "'": 0x34, "grave": 0x35, "`": 0x35,
    "comma": 0x36, ",": 0x36, "period": 0x37, ".": 0x37,
    "slash": 0x38, "/": 0x38, "capslock": 0x39,
    # 펑션
    "f1": 0x3A, "f2": 0x3B, "f3": 0x3C, "f4": 0x3D, "f5": 0x3E, "f6": 0x3F,
    "f7": 0x40, "f8": 0x41, "f9": 0x42, "f10": 0x43, "f11": 0x44, "f12": 0x45,
    # 편집/네비
    "insert": 0x49, "home": 0x4A, "pageup": 0x4B, "delete": 0x4C,
    "end": 0x4D, "pagedown": 0x4E,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "lang1": 0x90,   # 한/영 전환 (KS X 6369, 윈도우 한글 IME 한↔영 토글)
}

# Modifier 비트마스크 (byte0)
HID_MODIFIERS = {
    "ctrl": 0x01, "lctrl": 0x01, "rctrl": 0x10,
    "shift": 0x02, "lshift": 0x02, "rshift": 0x20,
    "alt": 0x04, "lalt": 0x04, "ralt": 0x40,
    "meta": 0x08, "lmeta": 0x08, "rmeta": 0x80,   # Win/Super(GUI)
    "gui": 0x08, "win": 0x08,
}

# ── 기호 → (베이스 키 이름, Shift 필요 여부) ───────────────────
#   미국(US) 표준 키보드 레이아웃 기준.
#   예: '*' = Shift + '8',  '!' = Shift + '1',  '/' 는 Shift 없이 슬래시 키.
#   HID 키코드는 베이스 키(숫자/문자/기호키)에 매핑되고, Shift 여부로 윗글자 결정.
SYMBOL_TO_KEY = {
    # 숫자열 윗글자 (Shift + 숫자)
    "!": ("1", True), "@": ("2", True), "#": ("3", True), "$": ("4", True),
    "%": ("5", True), "^": ("6", True), "&": ("7", True), "*": ("8", True),
    "(": ("9", True), ")": ("0", True),
    # 기호 키들 (Shift 없는 글자 / Shift 있는 윗글자)
    "-": ("-", False), "_": ("-", True),
    "=": ("=", False), "+": ("=", True),
    "[": ("[", False), "{": ("[", True),
    "]": ("]", False), "}": ("]", True),
    "\\": ("\\", False), "|": ("\\", True),
    ";": (";", False), ":": (";", True),
    "'": ("'", False), "\"": ("'", True),
    "`": ("`", False), "~": ("`", True),
    ",": (",", False), "<": (",", True),
    ".": (".", False), ">": (".", True),
    "/": ("/", False), "?": ("/", True),
}


# ═══════════════════════════════════════════════════════════════════════════
# 2. 한글 자모 → 두벌식 QWERTY 키 시퀀스 매핑
#    타겟 PC가 두벌식 IME일 때, 낱자를 자판 위치 키로 보내면 IME가 조합한다.
#    겹받침/복모음은 2개 키로 분해된다. (예: ㅘ → h,k / ㄳ → r,t)
# ═══════════════════════════════════════════════════════════════════════════
# 단일 자모 → 키 (소문자=평음, 대문자=Shift 필요한 쌍자음/된소리)
# 두벌식 표준 배열 기준.
JAMO_TO_QWERTY = {
    # ── 자음(초성/종성 공통 낱자) ──
    "ㄱ": "r",  "ㄲ": "R",  "ㄴ": "s",  "ㄷ": "e",  "ㄸ": "E",
    "ㄹ": "f",  "ㅁ": "a",  "ㅂ": "q",  "ㅃ": "Q",  "ㅅ": "t",
    "ㅆ": "T",  "ㅇ": "d",  "ㅈ": "w",  "ㅉ": "W",  "ㅊ": "c",
    "ㅋ": "z",  "ㅌ": "x",  "ㅍ": "v",  "ㅎ": "g",
    # ── 모음 ──
    "ㅏ": "k",  "ㅐ": "o",  "ㅑ": "i",  "ㅒ": "O",  "ㅓ": "j",
    "ㅔ": "p",  "ㅕ": "u",  "ㅖ": "P",  "ㅗ": "h",  "ㅛ": "y",
    "ㅜ": "n",  "ㅠ": "b",  "ㅡ": "m",  "ㅣ": "l",
    # ── 복합 모음(2키 분해) ──
    "ㅘ": "hk", "ㅙ": "ho", "ㅚ": "hl", "ㅝ": "nj", "ㅞ": "np",
    "ㅟ": "nl", "ㅢ": "ml",
    # ── 겹받침(2키 분해) ──
    "ㄳ": "rt", "ㄵ": "sw", "ㄶ": "sg", "ㄺ": "fr", "ㄻ": "fa",
    "ㄼ": "fq", "ㄽ": "ft", "ㄾ": "fx", "ㄿ": "fv", "ㅀ": "fg",
    "ㅄ": "qt",
}


def decompose_hangul(ch: str):
    """
    완성형 한글 1글자를 (초성, 중성, 종성) 자모로 분해.
    한글 음절이 아니면 None.
    """
    code = ord(ch)
    if not (HANGUL_BASE <= code <= HANGUL_BASE + 11171):
        return None
    idx = code - HANGUL_BASE
    cho = idx // (21 * 28)
    jung = (idx % (21 * 28)) // 28
    jong = idx % 28
    cho_c = CHOSUNG[cho]
    jung_c = JUNGSUNG[jung]
    jong_c = JONGSUNG[jong]  # '' 가능
    return cho_c, jung_c, jong_c


def hangul_to_qwerty_keys(ch: str):
    """
    한글 1글자 → 두벌식 자판 키 시퀀스(리스트).
    예) '가' → ['r','k'],  '값' → ['r','k','q','t'],  '왜' → ['d','h','o']? (ㅇㅘㅐ→ㅙ)
    완성형이 아니면:
      - 낱자모(ㄱ~ㅎ, ㅏ~ㅣ 등 호환 자모)면 두벌식 키로 변환
      - 그 외(영문/숫자/기호)는 글자 자체를 1키로 반환
    """
    parts = decompose_hangul(ch)
    if parts is None:
        # 완성형 한글이 아님 → 낱자모인지 먼저 확인
        if ch in JAMO_TO_QWERTY:
            # 단일 자모(예: 'ㅂ'→'q', 'ㅏ'→'k'). 복합키(예: 'ㅘ'→'hk')도 처리됨
            return list(JAMO_TO_QWERTY[ch])
        # 영문/숫자/기호 등은 그대로
        return [ch]
    cho, jung, jong = parts
    seq = ""
    for jamo in (cho, jung, jong):
        if not jamo:
            continue
        seq += JAMO_TO_QWERTY.get(jamo, "")
    return list(seq)


# ═══════════════════════════════════════════════════════════════════════════
# 3. HID 리포트 생성 / 전송 백엔드
# ═══════════════════════════════════════════════════════════════════════════
class HIDGadget:
    """
    /dev/hidg0(키보드), /dev/hidg1(마우스)에 raw 리포트를 기록.
    장치 파일이 없으면(개발 PC) 폴백: 콘솔에 리포트를 출력.
    """

    def __init__(self):
        self.kbd = self._open(HIDG_KEYBOARD)
        self.mouse = self._open(HIDG_MOUSE)
        self.fallback_kbd = self.kbd is None
        self.fallback_mouse = self.mouse is None
        # 현재 눌려있는 마우스 버튼 비트(드래그 중 이동 리포트에 함께 실음)
        self._mouse_button_state = 0x00
        if self.fallback_kbd or self.fallback_mouse:
            print("[INFO] HID 가젯 일부/전체 폴백(콘솔 출력) 모드. "
                  "실제 전송은 /dev/hidg* 가 있을 때만 발생합니다.")

    @staticmethod
    def _open(path):
        try:
            # 바이너리 쓰기, 버퍼링 없음
            return open(path, "wb", buffering=0)
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"[INFO] {path} 열기 실패({e}). 폴백 사용.")
            return None

    # ── 키보드 리포트(8바이트) ─────────────────────────────
    def _write_kbd(self, modifier=0, keycode=0):
        report = bytes([modifier & 0xFF, 0x00, keycode & 0xFF, 0, 0, 0, 0, 0])
        if self.kbd is None:
            print(f"   [HIDG0] mod=0x{modifier:02x} key=0x{keycode:02x}")
            return
        try:
            self.kbd.write(report)
            self.kbd.flush()
        except OSError as e:
            print(f"[HIDG0-ERROR] write 실패: {e}")

    def send_key(self, keycode, modifier=0):
        """단일 키 누름→떼기 1회."""
        self._write_kbd(modifier, keycode)      # press
        time.sleep(KEY_PRESS_INTERVAL)
        self._write_kbd(0, 0)                    # release (all up)
        time.sleep(KEY_PRESS_INTERVAL)

    def send_char_key(self, ch):
        """
        문자 1개를 HID로. 대문자/Shift기호면 Shift modifier 자동 적용.
        QWERTY 키 문자(a-z, 0-9, 기호) 기준.
        """
        if ch == "":
            return
        mod = 0
        c = ch
        if ch.isupper():
            mod = HID_MODIFIERS["shift"]
            c = ch.lower()
        elif ch in SYMBOL_TO_KEY:
            c, need_shift = SYMBOL_TO_KEY[ch]
            if need_shift:
                mod = HID_MODIFIERS["shift"]
        keycode = HID_KEYCODES.get(c)
        if keycode is None:
            # 매핑 없는 문자는 스킵(안전)
            print(f"   [SKIP] HID 키코드 없음: {ch!r}")
            return
        self.send_key(keycode, mod)

    # ── 마우스 리포트(4바이트, 표준 규격) ──────────────────
    #   byte0 = 버튼 비트 (bit0=좌 0x01, bit1=우 0x02, bit2=중간 0x04)
    #   byte1 = X 이동 (int8, -127~127)
    #   byte2 = Y 이동 (int8)
    #   byte3 = 휠     (int8)
    def _write_mouse(self, buttons=0, dx=0, dy=0, wheel=0, debug=False):
        def i8(v):
            v = max(-127, min(127, int(v)))
            return v & 0xFF
        report = bytes([buttons & 0xFF, i8(dx), i8(dy), i8(wheel)])
        if self.mouse is None:
            if buttons or dx or dy or wheel:
                print(f"   [HIDG1-FALLBACK] {report.hex(' ')} "
                      f"(btn={buttons} dx={dx} dy={dy} wheel={wheel})")
            return
        try:
            self.mouse.write(report)
            # 커널 버퍼에 머물지 않고 즉시 호스트로 전달되도록 강제 flush.
            # (특히 클릭 release 처럼 마지막 1회성 리포트는 flush 가 없으면 지연될 수 있음)
            self.mouse.flush()
            if debug:
                print(f"   [HIDG1-SEND] {report.hex(' ')}")
        except OSError as e:
            print(f"[HIDG1-ERROR] write 실패: {e}")

    def mouse_move(self, dx, dy):
        # 이동 리포트에도 현재 눌려있는 버튼 상태(self._mouse_button_state)를
        # 함께 실어, 드래그 중 버튼이 풀리지 않도록 한다.
        if dx or dy:
            self._write_mouse(self._mouse_button_state, dx, dy, 0)

    def mouse_click(self, button="left"):
        """
        표준 4바이트 마우스 리포트로 클릭을 전송한다.
          좌클릭 press : 01 00 00 00   → release : 00 00 00 00
          우클릭 press : 02 00 00 00   → release : 00 00 00 00
        press 를 충분히 유지(MOUSE_CLICK_PRESS_MS)한 뒤 release 를 보내며,
        호출부에서 클릭 동안 이동 송신을 보류해 press 가 덮이지 않게 한다.
        """
        bit = 0x01 if button == "left" else (0x02 if button == "right" else 0x04)
        # press: 버튼 비트만 세팅, 이동량 0  (debug=True 로 실제 바이트 출력)
        self._mouse_button_state = bit
        self._write_mouse(bit, 0, 0, 0, debug=True)
        time.sleep(MOUSE_CLICK_PRESS_MS)
        # release: 모든 바이트 0 (버튼 떼기)
        self._mouse_button_state = 0x00
        self._write_mouse(0x00, 0, 0, 0, debug=True)
        time.sleep(MOUSE_CLICK_RELEASE_MS)

    def cleanup(self):
        for f in (self.kbd, self.mouse):
            try:
                if f is not None:
                    f.close()
            except Exception:  # noqa: BLE001
                pass


# ═══════════════════════════════════════════════════════════════════════════
# 4. Key Dispatcher — 정규화 문자열 → HID 키보드 리포트
#    'ctrl+c' → modifier(ctrl) + keycode(c) 동시 전송.
# ═══════════════════════════════════════════════════════════════════════════
class HIDKeyDispatcher:
    """config.json 매핑 문자열(ctrl+c 등)을 HID 키 리포트로 변환·전송."""

    def __init__(self, hid: HIDGadget):
        self.hid = hid

    def dispatch(self, value: str):
        if not value or value == "MODE_SWITCH":
            return
        try:
            # (1) 값 전체가 단일 기호인 경우 먼저 처리.
            #     '+' 자체도 여기서 잡아야 split('+') 로 깨지지 않는다.
            if value in SYMBOL_TO_KEY:
                base, need_shift = SYMBOL_TO_KEY[value]
                kc = HID_KEYCODES.get(base)
                if kc is not None:
                    mod = HID_MODIFIERS["shift"] if need_shift else 0
                    self.hid.send_key(kc, mod)
                return

            # (2) 단일 일반 글자(영문/숫자)인 경우.
            if len(value) == 1 and value in HID_KEYCODES:
                self.hid.send_key(HID_KEYCODES[value], 0)
                return
            if len(value) == 1 and value.isalpha():
                # 대문자 알파벳 → shift + 소문자
                kc = HID_KEYCODES.get(value.lower())
                if kc is not None:
                    mod = HID_MODIFIERS["shift"] if value.isupper() else 0
                    self.hid.send_key(kc, mod)
                return

            # (3) 조합키(ctrl+c 등). '+' 로 분리.
            tokens = [t.strip() for t in value.split("+") if t.strip()]
            if not tokens:
                return
            modifier = 0
            keycode = 0
            for t in tokens:
                tl = t.lower()
                if tl in HID_MODIFIERS:
                    modifier |= HID_MODIFIERS[tl]
                elif t in SYMBOL_TO_KEY:
                    # 조합 안에 기호가 온 경우 (예: ctrl+/ )
                    base, need_shift = SYMBOL_TO_KEY[t]
                    kc = HID_KEYCODES.get(base)
                    if kc is not None:
                        keycode = kc
                        if need_shift:
                            modifier |= HID_MODIFIERS["shift"]
                else:
                    kc = HID_KEYCODES.get(tl)
                    if kc is not None:
                        keycode = kc      # 마지막 일반 키 1개 사용
                    else:
                        print(f"   [SKIP] 매크로 키코드 없음: {t!r}")
            self.hid.send_key(keycode, modifier)
        except Exception as e:  # noqa: BLE001
            print(f"   [DISPATCH-ERROR] '{value}': {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 5. config.json 로더 (커스텀 모드 매크로)
# ═══════════════════════════════════════════════════════════════════════════
def load_macro_config():
    """config.json 로드. 성공 시 dict, 실패(파일 없음/JSON 깨짐) 시 None."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}
    except FileNotFoundError:
        print(f"[WARN] config.json 없음 ({CONFIG_PATH}).")
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] config.json 로드 실패: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 6. 천지인 '스위치 번호' → 엔진 토큰 매핑  (실제 배선도 기능 기준)
# ═══════════════════════════════════════════════════════════════════════════
#  엔진(CheonjiinEngine)의 자음 토글표:
#    5=ㄱ/ㅋ 6=ㄴ/ㄹ 7=ㄷ/ㅌ 8=ㅂ/ㅍ 9=ㅅ/ㅎ 0=ㅈ/ㅊ 4=ㅁ/ㅇ
#    모음 1=ㅣ 2=ㆍ 3=ㅡ / 영어순환 10,11
#  배선도의 스위치 기능을 위 엔진 토큰에 대응시킨다.
#  (한/영=12, Shift=13, 커스텀=16, Enter=8 은 아래에서 특수 처리)
KEYID_TO_ENGINE_TOKEN = {
    1: "1",      # 스위치1  ㅣ
    2: "2",      # 스위치2  ㆍ
    3: "3",      # 스위치3  ㅡ
    4: "back",   # 스위치4  Backspace
    5: "5",      # 스위치5  ㄱ,ㅋ
    6: "6",      # 스위치6  ㄴ,ㄹ
    7: "7",      # 스위치7  ㄷ,ㅌ
    # 8 = Enter  → 특수 처리(SPECIAL_ENTER_KEY_ID)
    9: "8",      # 스위치9  ㅂ,ㅍ  (엔진 토큰 '8')
    10: "9",     # 스위치10 ㅅ,ㅎ  (엔진 토큰 '9')
    11: "0",     # 스위치11 ㅈ,ㅊ  (엔진 토큰 '0')
    # 12 = 한/영 → 특수 처리(HANGUL_TOGGLE_KEY_ID)
    # 13 = Shift → 특수 처리(SHIFT 는 GPIO 직접 감지)
    14: "4",     # 스위치14 ㅇ,ㅁ  (엔진 토큰 '4')
    15: "space", # 스위치15 Space
    # 16 = 커스텀 모드 → 특수 처리(FIXED_KEY_ID)
}
# 영어 멀티탭(v/w, x/y/z)은 어느 물리 스위치에 둘지 사용자가 정하면 추가.
# 우선 배선도의 한글 기능을 그대로 반영했다.

SPECIAL_ENTER_KEY_ID = 8     # 스위치8 = Enter (HID enter 직접 전송)
SHIFT_KEY_ID = 13            # 스위치13 = Shift(쌍자음). GPIO15 로도 감지.


# ═══════════════════════════════════════════════════════════════════════════
# 7. 하드웨어 입력 계층 (GPIO + MCP3008). 지연 임포트 + 폴백.
# ═══════════════════════════════════════════════════════════════════════════
class InputLayer:
    def __init__(self):
        self.buttons = {}
        self.shift_button = None
        self.joy_button = None
        self.spi = None
        self._init()

    def _init(self):
        # ── gpiozero 임포트 (한 번만) ──────────────────────
        Button = None
        try:
            from gpiozero import Button as _Button
            Button = _Button
        except Exception as e:  # noqa: BLE001
            print(f"[INFO] gpiozero 임포트 실패(폴백): {e}")
            print("      → sudo apt install python3-gpiozero (또는 pip install gpiozero lgpio)")

        if Button is not None:
            # ── 핵심: 버튼을 '하나씩 따로' 생성한다 ──────────
            #   예전 코드는 16개 키패드 버튼 + shift + 조이스틱을 한 try 로 묶어서,
            #   아직 배선 안 된 키패드 핀에서 에러가 나면 그 즉시 except 로 빠져
            #   조이스틱 버튼(joy_button)까지 생성되지 못했다.
            #   → 키패드가 아직 없어도 조이스틱/Shift 는 독립적으로 살아있어야 한다.

            # (1) 키패드 16개: 각각 개별 try. 실패한 핀만 건너뛴다.
            #     SHIFT_KEY_ID(13)는 shift_button으로 별도 생성하므로 여기서 건너뜀.
            ok_keys, fail_keys = [], []
            for key_id, pin in KEY_GPIO_MAP.items():
                if key_id == SHIFT_KEY_ID:   # GPIO 중복 생성 방지
                    continue
                try:
                    self.buttons[key_id] = Button(pin, pull_up=True, bounce_time=0.02)
                    ok_keys.append(key_id)
                except Exception as e:  # noqa: BLE001
                    fail_keys.append((key_id, pin, str(e)))
            if ok_keys:
                print(f"[OK] 키패드 버튼 생성: {len(ok_keys)}개 {ok_keys}")
            if fail_keys:
                # 키패드 미배선 단계에서는 정상적인 상황. 경고만 남기고 계속.
                print(f"[INFO] 키패드 버튼 {len(fail_keys)}개 미생성(미배선/사용중일 수 있음):")
                for key_id, pin, msg in fail_keys:
                    print(f"        - 스위치{key_id}(GPIO{pin}): {msg}")

            # (2) Shift 버튼: 독립 try
            try:
                self.shift_button = Button(SHIFT_GPIO, pull_up=True, bounce_time=0.02)
                print(f"[OK] Shift 버튼 생성 (GPIO{SHIFT_GPIO})")
            except Exception as e:  # noqa: BLE001
                print(f"[INFO] Shift 버튼(GPIO{SHIFT_GPIO}) 미생성: {e}")

            # (3) 조이스틱 버튼: 독립 try  ← 이게 살아야 클릭이 된다
            try:
                self.joy_button = Button(JOYSTICK_BTN_GPIO, pull_up=True, bounce_time=0.02)
                print(f"[OK] 조이스틱 버튼 생성 (GPIO{JOYSTICK_BTN_GPIO})  ← 클릭 담당")
            except Exception as e:  # noqa: BLE001
                print(f"[경고] 조이스틱 버튼(GPIO{JOYSTICK_BTN_GPIO}) 생성 실패: {e}")
                print("       → 이게 실패하면 마우스 클릭이 동작하지 않습니다.")

        # ── MCP3008 (SPI) ─────────────────────────────────
        try:
            import spidev
            self.spi = spidev.SpiDev()
            self.spi.open(0, 0)
            self.spi.max_speed_hz = 1_350_000
            print("[OK] MCP3008 SPI 연결")
        except Exception as e:  # noqa: BLE001
            print(f"[INFO] spidev 미사용(폴백): {e}")
            self.spi = None

    def read_adc(self, channel):
        if self.spi is None:
            return ADC_CENTER
        try:
            r = self.spi.xfer2([1, (8 + channel) << 4, 0])
            return ((r[1] & 3) << 8) | r[2]
        except Exception as e:  # noqa: BLE001
            print(f"[ADC-ERROR] ch{channel}: {e}")
            return ADC_CENTER

    def cleanup(self):
        try:
            if self.spi is not None:
                self.spi.close()
        except Exception:  # noqa: BLE001
            pass


# ═══════════════════════════════════════════════════════════════════════════
# 8. 메인 펌웨어 컨트롤러 (HID 출력 전용)
# ═══════════════════════════════════════════════════════════════════════════
class KeyboardFirmwareHID:
    MODE_INPUT = "INPUT"
    MODE_CUSTOM = "CUSTOM"

    def __init__(self):
        self.hid = HIDGadget()
        self.inp = InputLayer()
        self.dispatcher = HIDKeyDispatcher(self.hid)
        self.engine = CheonjiinEngine()
        self.macro_config = load_macro_config() or {}
        self.mouse_speed = MOUSE_SPEED
        self.right_click_hold = RIGHT_CLICK_HOLD

        self.mode = self.MODE_INPUT
        self._last_committed = ""
        self._sent_keys: list = []   # render-diff: 현재 윈도우 IME에 보낸 키 추적
        self._joy_pressed_at = None
        self._last_input_time = None
        self._bs_pressed_at = None
        self._bs_last_repeat = None
        self._config_mtime = self._get_config_mtime()
        self._config_check_at = 0.0
        self._running = True

        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

    def _on_signal(self, signum, frame):
        print(f"\n[SIGNAL] {signum} 수신 → 종료")
        self._running = False

    @staticmethod
    def _get_config_mtime():
        try:
            return os.path.getmtime(CONFIG_PATH)
        except OSError:
            return 0.0

    def _process_config_reload(self):
        now = time.monotonic()
        if (now - self._config_check_at) < CONFIG_CHECK_INTERVAL:
            return
        self._config_check_at = now
        mtime = self._get_config_mtime()
        if mtime == self._config_mtime:
            return
        new = load_macro_config()
        if new is None:
            # JSON 깨진 상태(쓰기 도중) → 기존 매핑 유지, mtime 갱신 안 함
            return
        self._config_mtime = mtime
        self.macro_config = new
        try:
            self.mouse_speed = int(new.get("mouse_speed", MOUSE_SPEED))
        except (ValueError, TypeError):
            self.mouse_speed = MOUSE_SPEED
        try:
            self.right_click_hold = float(new.get("right_click_hold", RIGHT_CLICK_HOLD))
        except (ValueError, TypeError):
            self.right_click_hold = RIGHT_CLICK_HOLD
        print(f"[CONFIG] 설정 자동 갱신됨 (mouse_speed={self.mouse_speed}, right_click_hold={self.right_click_hold})")

    # ── 모드 전환 ─────────────────────────────────────────
    def _toggle_custom_mode(self):
        self._flush_engine()
        if self.mode == self.MODE_INPUT:
            self.mode = self.MODE_CUSTOM
            new = load_macro_config()
            if new is not None:
                self.macro_config = new
            print("[MODE] → CUSTOM")
        else:
            self.mode = self.MODE_INPUT
            self.engine = CheonjiinEngine()
            self._last_committed = ""
            self._sent_keys = []
            print("[MODE] → INPUT")

    def _flush_engine(self):
        self.engine.press("space")
        self._emit_engine_output()

    # ── 엔진 출력 → HID 전송 (증분) ───────────────────────
    def _emit_engine_output(self):
        """
        엔진 출력 → 윈도우 HID 전송 (render-diff 방식).

        [committed 감소] HID backspace 전송.
        [committed 증가] space/enter/영문만 명시 전송.
                         한글은 render-diff가 즉시 처리하므로 재전송 안 함.
        [render 변화]    조합 중 글자를 매 stroke마다 즉시 윈도우에 반영.
                         이전 보낸 키와 diff 계산 → backspace + 새 키 전송.
                         ㆍ(아래아) 중간 상태는 두벌식 매핑 없어 스킵.
        """
        full = self.engine.committed
        prev_len = len(self._last_committed)
        curr_len = len(full)

        # ── 1. committed 감소: 확정 글자 삭제 ─────────────
        if curr_len < prev_len:
            diff = prev_len - curr_len
            for _ in range(diff):
                self.hid.send_key(HID_KEYCODES["backspace"])
            self._last_committed = full
            self._sent_keys = []
            return

        # ── 1.5 committed 동일 길이인데 내용 변경: 영어 사이클 치환 ─────────
        # EN 모드에서 같은 키 연속 입력 시 마지막 글자를 교체(a→b→c).
        # 길이는 그대로이므로 Section 1/2가 모두 스킵됨 → 명시적으로 처리.
        if curr_len == prev_len and curr_len > 0 and full != self._last_committed:
            common = 0
            for a, b in zip(full, self._last_committed):
                if a == b:
                    common += 1
                else:
                    break
            changed = curr_len - common
            for _ in range(changed):
                self.hid.send_key(HID_KEYCODES["backspace"])
            for ch in full[common:]:
                if ch == ' ':
                    self.hid.send_char_key('space')
                elif ord(ch) < 0x3000:
                    self.hid.send_char_key(ch)
            self._last_committed = full
            self._sent_keys = []
            return

        # ── 2. committed 증가: 새 글자 확정됨 ─────────────
        if curr_len > prev_len:
            new_text = full[prev_len:]
            self._last_committed = full

            # space / enter / 영문·기호(ASCII)만 명시 전송
            # 한글(가-힣, 자모)은 윈도우 IME가 render-diff 키로 자동 조합
            has_flush = False
            for ch in new_text:
                if ch == " ":
                    self.hid.send_char_key("space")
                    has_flush = True
                elif ch == "\n":
                    self.hid.send_key(HID_KEYCODES["enter"])
                    has_flush = True
                elif ord(ch) < 0x3000:      # ASCII 영문·기호
                    self.hid.send_char_key(ch)

            # 윈도우 IME 현재 조합 상태 추정
            if has_flush:
                # space/enter → IME 조합 강제 확정, 조합 버퍼 비워짐
                self._sent_keys = []
            elif self.engine.composer.jung:
                # 도깨비불: 이전 음절 받침이 새 음절 초성으로 이동.
                # 윈도우 IME도 모음 키를 받으면 동시에 도깨비불 처리.
                # → 새 초성이 이미 IME 조합에 들어간 것처럼 추적.
                new_cho = self.engine.composer.cho
                self._sent_keys = list(JAMO_TO_QWERTY.get(new_cho, ''))
            else:
                # 자음 치환(초성→초성) 또는 음절 완성 후 새 초성 시작:
                # 아직 아무것도 안 보낸 상태 → 빈 슬레이트
                self._sent_keys = []

        # ── 3. render-diff: 조합 중 글자 즉시 반영 ─────────
        render = self.engine.composer.render()

        if not render:
            if self.engine.composer.is_empty():
                # composer가 비어짐(undo로 초성 제거 등) → Windows IME 조합 잔여 키 정리
                for _ in range(len(self._sent_keys)):
                    self.hid.send_key(HID_KEYCODES["backspace"])
                self._sent_keys = []
            # else: ㆍ 중간 상태(render 비어도 composer 있음) → 스킵
            return

        new_keys = hangul_to_qwerty_keys(render)

        # 전송 불가 키 포함 여부 확인 (ㆍ 등 HID_KEYCODES에 없는 자모)
        def _ok(k):
            return (k.lower() if len(k) == 1 else k) in HID_KEYCODES

        if not all(_ok(k) for k in new_keys):
            return  # 전송 불가 자모(ㆍ 등) → 스킵

        if new_keys == self._sent_keys:
            return  # 변화 없음

        # 공통 접두사 길이 계산
        common_len = 0
        for a, b in zip(self._sent_keys, new_keys):
            if a == b:
                common_len += 1
            else:
                break

        # 이전 꼬리 제거 (backspace)
        for _ in range(len(self._sent_keys) - common_len):
            self.hid.send_key(HID_KEYCODES["backspace"])

        # 새 꼬리 전송
        for k in new_keys[common_len:]:
            self.hid.send_char_key(k)

        self._sent_keys = list(new_keys)

    # ── 기본 모드 키 처리 ─────────────────────────────────
    def _handle_input_mode(self, key_id, shift_held):
        if key_id == HANGUL_TOGGLE_KEY_ID:
            # 한/영 전환: 조합 중 글자만 확정(공백 미추가) → LANG1 전송 → 모드 토글
            # _flush_engine()은 빈 상태에서 space를 삽입하므로 직접 처리
            if not self.engine.composer.is_empty():
                self.engine.press("space")   # 비어있지 않을 때만 → 확정만, 공백 없음
                self._emit_engine_output()
            self._sent_keys = []
            self.hid.send_key(*HANGUL_HID)
            self.engine.press("mode")
            print(f"[INPUT] 한/영 전환 → [MODE: {self.engine.mode.upper()}]")
            return

        if key_id == SPECIAL_ENTER_KEY_ID:
            # Enter: 조립 중 글자를 확정해 전송한 뒤, HID Enter 키 전송
            self._flush_engine()
            self.hid.send_key(HID_KEYCODES["enter"])
            print("[INPUT] Enter")
            return

        token = KEYID_TO_ENGINE_TOKEN.get(key_id)
        if token is None:
            return
        if token == "back":
            # backspace: 엔진 상태가 완전히 비어있으면 윈도우로 직접 전달
            was_empty = self.engine.composer.is_empty() and not self.engine.committed
            self.engine.press("back")
            self._emit_engine_output()
            if was_empty and not self._sent_keys:
                self.hid.send_key(HID_KEYCODES["backspace"])
            self._show_input_state()
            return
        if shift_held:
            self.engine.press("s")   # 한글: 쌍자음 / 영어: 대문자
        self.engine.press(token)
        self._emit_engine_output()
        self._show_input_state()     # 현재 조합 상태를 화면에 표시

    def _show_input_state(self):
        """
        현재 입력 상태를 터미널에 한 줄로 보여준다.
          - 확정된 글자 + 조합 중인 글자를 표시.
          - 완성형으로 안 합쳐지는 중간 상태(예: ㄱ + 아래아ㆍ)는
            자모를 나란히 붙여서 'ㄱㆍ' 처럼 보여준다.
          - 예) ㄱ → ㄱㆍ → 거  /  ㄱ → ㅋ(토글)
        """
        committed = self.engine.committed
        composing = self._render_composing()
        line = f"{committed}[{composing}]" if composing else committed
        print(f"  입력 ▶ {line}")

    def _render_composing(self):
        """
        조합 중인 글자를 화면용으로 만든다.
        엔진의 render() 가 빈 문자열을 주는 중간 상태(초성+아래아 등)도
        자모를 직접 이어붙여 보이게 한다.
        """
        c = self.engine.composer
        r = c.render()
        if r:
            return r   # 정상 완성/부분 글자 ('ㄱ', '거', '간' 등)
        # render() 가 빈 문자열인 경우: 초성/중성 자모를 직접 이어붙임
        # (예: 초성 ㄱ + 중성 아래아 ㆍ → 'ㄱㆍ')
        parts = ""
        if c.cho:
            parts += c.cho
        if c.jung:
            parts += c.jung
        if c.jong:
            parts += c.jong
        return parts

    # ── 자동확정 타임아웃 ─────────────────────────────────
    def _process_auto_confirm(self):
        """조합 중인 상태에서 AUTO_CONFIRM_TIMEOUT 동안 무입력이면 자동 확정."""
        if self.engine.composer.is_empty():
            return
        if self._last_input_time is None:
            return
        if (time.monotonic() - self._last_input_time) >= AUTO_CONFIRM_TIMEOUT:
            self._flush_engine()
            self._emit_engine_output()
            self._show_input_state()
            self._last_input_time = None

    # ── backspace 연속삭제 폴링 ───────────────────────────
    def _process_backspace_hold(self):
        """backspace(스위치4)를 BS_HOLD_THRESHOLD 이상 누르면 연속 삭제."""
        btn = self.inp.buttons.get(4)
        if btn is None:
            return
        now = time.monotonic()
        if btn.is_pressed:
            if self._bs_pressed_at is None:
                self._bs_pressed_at = now
                self._bs_last_repeat = None
            elif (now - self._bs_pressed_at) >= BS_HOLD_THRESHOLD:
                if (self._bs_last_repeat is None
                        or (now - self._bs_last_repeat) >= BS_REPEAT_INTERVAL):
                    was_empty = self.engine.composer.is_empty() and not self.engine.committed
                    self.engine.press("back")
                    self._emit_engine_output()
                    if was_empty and not self._sent_keys:
                        self.hid.send_key(HID_KEYCODES["backspace"])
                    self._show_input_state()
                    self._bs_last_repeat = now
                    self._last_input_time = now   # 자동확정 타이머 리셋
        else:
            self._bs_pressed_at = None
            self._bs_last_repeat = None

    # ── 커스텀 모드 키 처리 ───────────────────────────────
    def _handle_custom_mode(self, key_id):
        value = self.macro_config.get(str(key_id), "")
        if not value or value == "MODE_SWITCH":
            return
        print(f"[CUSTOM] {key_id}번 → '{value}'")
        self.dispatcher.dispatch(value)

    # ── 키 눌림 진입점 ────────────────────────────────────
    def on_key_press(self, key_id, shift_held=False):
        self._last_input_time = time.monotonic()   # 자동확정 타이머 갱신
        if key_id == FIXED_KEY_ID:
            self._toggle_custom_mode()
            return
        if self.mode == self.MODE_INPUT:
            self._handle_input_mode(key_id, shift_held)
        else:
            self._handle_custom_mode(key_id)

    # ── 조이스틱 → 마우스 HID ─────────────────────────────
    def _process_joystick(self):
        x = self.inp.read_adc(ADC_CH_X)
        y = self.inp.read_adc(ADC_CH_Y)
        dx = self._axis_to_delta(x)
        dy = self._axis_to_delta(y)
        if dx or dy:
            self.hid.mouse_move(dx, dy)

    def _axis_to_delta(self, value):
        offset = value - ADC_CENTER
        if abs(offset) < ADC_DEADZONE:
            return 0
        ratio = offset / ADC_CENTER
        return int(ratio * self.mouse_speed)

    def _process_joystick_button(self):
        """
        버튼 상태를 폴링한다. 짧게=좌클릭, 길게=우클릭.
        클릭(press+release)을 실제로 발사한 루프에서는 True 를 반환하여,
        호출부가 같은 주기의 마우스 '이동' 송신을 건너뛰도록 한다.
        (이동 리포트가 직전 press/release 리포트를 즉시 덮어쓰는 것을 방지)

        gpiozero.Button(23, pull_up=True) 는 active-low 를 내부 보정하므로
        '버튼을 누르면(=GND로 떨어지면) is_pressed == True' 이다. 즉 아래 조건문은
        하드웨어 배선(Pull-up, 누르면 LOW)과 정확히 일치한다.
        """
        btn = self.inp.joy_button
        if btn is None:
            return False

        pressed = btn.is_pressed
        if pressed:
            # 버튼이 눌려있는 동안: 누름 시작 시각만 1회 기록
            if self._joy_pressed_at is None:
                print("[DEBUG] 조이스틱 버튼 눌림 감지!")
                self._joy_pressed_at = time.monotonic()
            return False
        else:
            # 버튼이 떼어진 순간: 직전에 눌려있었다면 클릭 발사
            if self._joy_pressed_at is not None:
                held = time.monotonic() - self._joy_pressed_at
                self._joy_pressed_at = None
                if held >= self.right_click_hold:
                    print(f"[DEBUG] 우클릭 HID 레포트 송신! (hold={held*1000:.0f}ms)")
                    self.hid.mouse_click("right")
                else:
                    print(f"[DEBUG] 좌클릭 HID 레포트 송신! (hold={held*1000:.0f}ms)")
                    self.hid.mouse_click("left")
                return True
            return False

    def _bind_gpio_callbacks(self):
        if not self.inp.buttons:
            return
        for key_id, btn in self.inp.buttons.items():
            btn.when_pressed = (
                lambda k=key_id: self.on_key_press(
                    k, shift_held=(self.inp.shift_button is not None
                                   and self.inp.shift_button.is_pressed)))
        # 스위치13(Shift) 은 self.buttons 에서 제외됐으므로 여기서 별도 등록.
        # 커스텀 모드에서만 on_key_press(13) 호출; 한글 입력 모드에서는 shift_held
        # 폴링으로 처리되므로 when_pressed 는 아무것도 안 한다.
        if self.inp.shift_button is not None:
            self.inp.shift_button.when_pressed = (
                lambda: self.on_key_press(SHIFT_KEY_ID)
                if self.mode == self.MODE_CUSTOM else None)

    # ── 메인 루프 ─────────────────────────────────────────
    def run(self):
        print("═" * 60)
        print(" 천지인 USB HID 키보드 펌웨어 시작")
        print(f"  - 모드: {self.mode}")
        print(f"  - 한/영: [MODE: {self.engine.mode.upper()}]  ← Windows IME도 이 상태여야 함")
        print("  - 동기화 확인: Windows 표시줄 IME가 '한'이면 OK, 'A'이면 노트북 한/영키 1회")
        print(f"  - 키보드 장치: {'OK' if self.hid.kbd else '폴백'} ({HIDG_KEYBOARD})")
        print(f"  - 마우스 장치: {'OK' if self.hid.mouse else '폴백'} ({HIDG_MOUSE})")
        joy_ok = self.inp.joy_button is not None
        print(f"  - 조이스틱 버튼(GPIO{JOYSTICK_BTN_GPIO}): "
              f"{'연결됨(pull_up)' if joy_ok else '폴백(미연결)'}")
        print(f"  - 매크로 매핑 {len(self.macro_config)}개")
        try:
            _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _s.connect(("8.8.8.8", 80))
            _ip = _s.getsockname()[0]
            _s.close()
        except Exception:
            _ip = "(IP 확인 실패)"
        _web = ThreadingHTTPServer(("0.0.0.0", 8000), SetterHandler)
        threading.Thread(target=_web.serve_forever, daemon=True).start()
        print(f"  - 웹 설정 서버: http://{_ip}:8000  ← 노트북 브라우저에서 접속")
        print("═" * 60)
        self._bind_gpio_callbacks()
        try:
            while self._running:
                self._process_backspace_hold()
                self._process_auto_confirm()
                self._process_config_reload()
                # 버튼을 먼저 처리. 이번 주기에 클릭(press+release)을 발사했다면
                # 같은 주기의 이동 송신은 건너뛰어 클릭 리포트를 보존한다.
                clicked = self._process_joystick_button()
                if not clicked:
                    self._process_joystick()
                time.sleep(LOOP_DELAY)
        except Exception as e:  # noqa: BLE001
            print(f"[FATAL] 메인 루프 예외: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        print("[SHUTDOWN] 정리 중…")
        try:
            self._flush_engine()
        except Exception:  # noqa: BLE001
            pass
        self.hid.cleanup()
        self.inp.cleanup()
        print("[SHUTDOWN] 완료.")


def main():
    KeyboardFirmwareHID().run()


if __name__ == "__main__":
    main()


# ═══════════════════════════════════════════════════════════════════════════
# [참고] HID 가젯 권한 & 부팅 자동 실행
#   /dev/hidg0, /dev/hidg1 쓰기에는 보통 root 권한이 필요하다.
#   따라서 sudo 로 실행하거나 아래 systemd 서비스(User=root)로 등록한다.
#
#   1) sudo nano /etc/systemd/system/cheonjiin.service
#
#      [Unit]
#      Description=Cheonjiin 16-key USB HID Keyboard Firmware
#      After=multi-user.target
#
#      [Service]
#      Type=simple
#      User=root
#      ExecStart=/usr/bin/python3 /home/pi/cheonjiin/main.py
#      Restart=on-failure
#      RestartSec=3
#
#      [Install]
#      WantedBy=multi-user.target
#
#   2) sudo systemctl daemon-reload
#      sudo systemctl enable cheonjiin.service
#      sudo systemctl start cheonjiin.service
#
#   3) 로그 확인:  journalctl -u cheonjiin.service -f
#      (디버그 로그 [DEBUG] ... 가 여기에 출력된다)
# ═══════════════════════════════════════════════════════════════════════════