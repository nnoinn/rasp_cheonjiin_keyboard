#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_setter.py — 웹 기반 키 커스텀 설정 페이지
════════════════════════════════════════════════════════════════
라즈베리파이 안에서 작은 웹 서버를 띄워, 같은 네트워크의 노트북/폰
브라우저에서 16키 매핑을 커스텀하고 config.json 에 저장한다.

- 파이썬 표준 라이브러리(http.server, json)만 사용. 추가 설치 불필요.
- gui_setter.py 의 정규화 로직/프리셋을 그대로 가져와 펌웨어와 호환.
- config.json 은 main.py 와 공유한다. 웹에서 저장 → 펌웨어가 읽음.

실행:  python3 web_setter.py      (기본 포트 8000)
       sudo 가 꼭 필요하진 않다(파일 쓰기 권한만 있으면 됨).

접속:  노트북 브라우저에서  http://<라즈베리파이IP>:8000
       예) http://192.168.45.11:8000
       (노트북과 라즈베리파이가 같은 와이파이에 있어야 함)

종료:  Ctrl+C
════════════════════════════════════════════════════════════════
"""

import json
import os
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ─────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
PORT = 8000

TOTAL_KEYS = 16
FIXED_KEY_ID = 16
FIXED_VALUE = "MODE_SWITCH"

# 배선도 기준 각 스위치의 기능 설명(화면 표시용). main.py 핀맵과 동일 순서.
KEY_FUNCTION_LABEL = {
    1:  "ㅣ / a,b,c",
    2:  "ㆍ(아래아) / d,e,f",
    3:  "ㅡ / g,h,i",
    4:  "Backspace",
    5:  "ㄱ,ㅋ / j,k,l",
    6:  "ㄴ,ㄹ / m,n,o",
    7:  "ㄷ,ㅌ / p,q,r",
    8:  "Enter",
    9:  "ㅂ,ㅍ / s,t,u",
    10: "ㅅ,ㅎ / v,w",
    11: "ㅈ,ㅊ / x,y,z",
    12: "한/영 전환",
    13: "Shift (쌍자음)",
    14: "ㅇ,ㅁ / 특수문자",
    15: "Space",
    16: "커스텀 모드 전환 (고정)",
}

# ─────────────────────────────────────────────────────────────
# 키 정규화 (gui_setter.py 와 동일 규칙)
# ─────────────────────────────────────────────────────────────
MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl", "^": "ctrl",
    "shift": "shift", "shft": "shift",
    "alt": "alt", "option": "alt", "opt": "alt",
    "meta": "meta", "cmd": "meta", "command": "meta",
    "win": "meta", "super": "meta",
}
MODIFIER_ORDER = ["ctrl", "shift", "alt", "meta"]
KEY_ALIASES = {
    "esc": "esc", "escape": "esc",
    "return": "enter", "enter": "enter",
    "del": "delete", "delete": "delete",
    "bksp": "backspace", "backspace": "backspace",
    "spacebar": "space", "space": "space",
    "pgup": "pageup", "pgdn": "pagedown",
}

# 단일 입력으로 허용되는 특수문자(미국 키보드 전체). 정규화에서 그대로 보존한다.
SINGLE_SYMBOLS = set("!@#$%^&*()-_=+[]{}\\|;:'\"`~,<.>/?")


def normalize_key(value: str) -> str:
    """자유 입력 → 'modifier+key' 표준형. 빈 값이면 ''."""
    if value is None:
        return ""
    s = value.strip()
    if not s:
        return ""
    if s == FIXED_VALUE:
        return FIXED_VALUE
    # 단일 특수문자(예: '+', '*', '-', '?')는 변형 없이 그대로 보존
    if len(s) == 1 and s in SINGLE_SYMBOLS:
        return s
    # 단일 영문/숫자도 그대로(대문자는 소문자로 통일하지 않음: shift 의미 보존)
    if len(s) == 1:
        return s
    for sep in ("-", "_", " "):
        s = s.replace(sep, "+")
    while "++" in s:
        s = s.replace("++", "+")
    s = s.strip("+").lower()
    if not s:
        return ""
    tokens = [t for t in s.split("+") if t]
    if not tokens:
        return ""
    mods, keys = [], []
    for t in tokens:
        if t in MODIFIER_ALIASES:
            std = MODIFIER_ALIASES[t]
            if std not in mods:
                mods.append(std)
        else:
            keys.append(KEY_ALIASES.get(t, t))
    mods_sorted = [m for m in MODIFIER_ORDER if m in mods]
    if not keys:
        return "+".join(mods_sorted) if mods_sorted else tokens[-1]
    return "+".join(mods_sorted + [keys[-1]])


DEFAULT_MAPPING = {
    # 캡처 기준 숫자패드 기본 배열
    "1": "7",  "2": "8",  "3": "9",  "4": "backspace",
    "5": "4",  "6": "5",  "7": "6",  "8": "enter",
    "9": "1",  "10": "2", "11": "3", "12": "-",          # 12 = 마이너스
    "13": "+", "14": "0", "15": "space",
    "16": FIXED_VALUE,
}

# 프리셋: (표시 라벨, 저장값). 라벨은 UI 표시 전용 — 저장값(value)이 config.json에 기록됨.
PRESET_ITEMS = [
    ("복사",       "ctrl+c"),
    ("붙여넣기",   "ctrl+v"),
    ("잘라내기",   "ctrl+x"),
    ("실행취소",   "ctrl+z"),
    ("다시실행",   "ctrl+y"),
    ("전체선택",   "ctrl+a"),
    ("저장",       "ctrl+s"),
    ("찾기",       "ctrl+f"),
    ("창닫기",     "alt+f4"),
    ("↑",         "up"),
    ("↓",         "down"),
    ("←",         "left"),
    ("→",         "right"),
    ("Enter",     "enter"),
    ("Backspace", "backspace"),
    ("Tab",       "tab"),
    ("Esc",       "esc"),
    ("Space",     "space"),
]


JOYSTICK_DEFAULTS = {"mouse_speed": 10, "right_click_hold": 0.5}

# ─────────────────────────────────────────────────────────────
# config.json 입출력
# ─────────────────────────────────────────────────────────────
def load_joystick_config():
    """config.json에서 조이스틱 설정만 읽기. 없거나 손상이면 기본값."""
    result = dict(JOYSTICK_DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            result["mouse_speed"] = int(data["mouse_speed"])
        except (KeyError, ValueError, TypeError):
            pass
        try:
            result["right_click_hold"] = float(data["right_click_hold"])
        except (KeyError, ValueError, TypeError):
            pass
    except (json.JSONDecodeError, OSError):
        pass
    return result


def save_joystick_config(joy):
    """mouse_speed / right_click_hold만 config.json에 머지 저장."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}
    try:
        data["mouse_speed"] = int(joy.get("mouse_speed", JOYSTICK_DEFAULTS["mouse_speed"]))
    except (ValueError, TypeError):
        data["mouse_speed"] = JOYSTICK_DEFAULTS["mouse_speed"]
    try:
        data["right_click_hold"] = float(joy.get("right_click_hold", JOYSTICK_DEFAULTS["right_click_hold"]))
    except (ValueError, TypeError):
        data["right_click_hold"] = JOYSTICK_DEFAULTS["right_click_hold"]
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_config():
    """config 로드. 없거나 손상 시 기본값 생성. 로드값도 정규화."""
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_MAPPING)
        return dict(DEFAULT_MAPPING)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        save_config(DEFAULT_MAPPING)
        return dict(DEFAULT_MAPPING)
    mapping = dict(DEFAULT_MAPPING)
    if isinstance(data, dict):
        for k, v in data.items():
            if k in mapping and k != str(FIXED_KEY_ID):
                norm = normalize_key(str(v))
                mapping[k] = norm if norm else mapping[k]
    mapping[str(FIXED_KEY_ID)] = FIXED_VALUE
    return mapping


def save_config(mapping):
    """정규화하여 config.json 저장(1~16 순서, indent=4). 조이스틱 설정 키는 항상 보존."""
    joy = load_joystick_config()  # 기존 조이스틱 설정 읽기 (없거나 손상이면 기본값)
    out = {}
    for i in range(1, TOTAL_KEYS + 1):
        key = str(i)
        if key == str(FIXED_KEY_ID):
            out[key] = FIXED_VALUE
        else:
            out[key] = normalize_key(str(mapping.get(key, "")))
    out["mouse_speed"] = joy["mouse_speed"]
    out["right_click_hold"] = joy["right_click_hold"]
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)


# ─────────────────────────────────────────────────────────────
# HTML 렌더링
# ─────────────────────────────────────────────────────────────
def render_page(mapping, status=None):
    preset_val_to_lbl = {val: lbl for lbl, val in PRESET_ITEMS}
    joy = load_joystick_config()
    joy_ms  = joy["mouse_speed"]
    joy_rch = joy["right_click_hold"]

    # ── 16키 그리드 셀
    cells = ""
    for i in range(1, TOTAL_KEYS + 1):
        key    = str(i)
        val    = mapping.get(key, "")
        func_e = html.escape(KEY_FUNCTION_LABEL.get(i, ""))

        if i == FIXED_KEY_ID:
            cells += (
                f'<div class="cell fixed">'
                f'<span class="knum">{i}</span>'
                f'<span class="kfunc">{func_e}</span>'
                f'<div class="badge-fixed">고정</div>'
                f'</div>'
            )
        elif val in preset_val_to_lbl:
            lbl_e = html.escape(preset_val_to_lbl[val])
            val_e = html.escape(val)
            cells += (
                f'<div class="cell locked" data-key="{i}">'
                f'<span class="knum">{i}</span>'
                f'<span class="kfunc">{func_e}</span>'
                f'<div class="badge">'
                f'<span class="badge-lbl">{lbl_e}</span>'
                f'<span class="badge-val">{val_e}</span>'
                f'</div>'
                f'<input type="hidden" name="key{i}" value="{val_e}" />'
                f'<button type="button" class="btn-x" onclick="unlockCell(this.parentElement)">&times;</button>'
                f'</div>'
            )
        else:
            val_e = html.escape(val)
            cells += (
                f'<div class="cell" data-key="{i}">'
                f'<span class="knum">{i}</span>'
                f'<span class="kfunc">{func_e}</span>'
                f'<input type="text" name="key{i}" value="{val_e}"'
                f' maxlength="1" autocomplete="off" placeholder="a" />'
                f'</div>'
            )

    # ── datalist (text input 자동완성)
    datalist = "".join(
        f'<option value="{html.escape(v)}">{html.escape(l)}</option>'
        for l, v in PRESET_ITEMS
    )

    # ── 카드 트레이 (그룹별)
    _pm = {v: l for l, v in PRESET_ITEMS}
    _groups = [
        ("클립보드", ["ctrl+c", "ctrl+v", "ctrl+x"]),
        ("편집",    ["ctrl+z", "ctrl+y", "ctrl+a", "ctrl+s", "ctrl+f", "alt+f4"]),
        ("방향키",  ["up", "down", "left", "right"]),
        ("기본키",  ["enter", "backspace", "tab", "esc", "space"]),
    ]
    cards = ""
    for _glbl, _vals in _groups:
        _items = "".join(
            f'<div class="card" data-value="{html.escape(v)}">'
            f'<span class="card-lbl">{html.escape(_pm[v])}</span>'
            f'<span class="card-val">{html.escape(v)}</span>'
            f'</div>'
            for v in _vals
        )
        cards += (
            f'<div class="card-group">'
            f'<span class="card-group-lbl">{html.escape(_glbl)}</span>'
            f'<div class="card-group-items">{_items}</div>'
            f'</div>'
        )

    # ── 배너
    if status == "saved":
        banner = '<div class="banner" id="banner">키 설정이 저장됐습니다 — 1초 안에 자동 반영됩니다.</div>'
    elif status == "reset":
        banner = '<div class="banner" id="banner">기본값으로 초기화됐습니다.</div>'
    elif status == "joy_saved":
        banner = '<div class="banner" id="banner">조이스틱 설정이 저장됐습니다 — 1초 안에 자동 반영됩니다.</div>'
    else:
        banner = ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>천지인 키보드 설정</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #e5e5ea;
  color: #1d1d1f;
  font-family: -apple-system, "SF Pro Display", "Noto Sans KR", "Helvetica Neue", sans-serif;
  -webkit-font-smoothing: antialiased;
  font-size: 15px; min-height: 100vh; padding: 56px 20px 88px;
}}
h1 {{
  text-align: center; font-size: 30px; font-weight: 700;
  letter-spacing: -0.03em; color: #1d1d1f; margin-bottom: 10px;
}}
.sub {{ text-align: center; color: #6e6e73; font-size: 16px; margin-bottom: 44px; font-weight: 400; }}
.banner {{
  max-width: 680px; margin: 0 auto 28px; padding: 13px 20px;
  background: #fff; border-radius: 14px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 12px 32px rgba(0,0,0,0.08);
  color: #6e6e73; text-align: center; font-size: 13px;
}}
.grid {{
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 12px; max-width: 680px; margin: 0 auto 18px;
}}
.cell {{
  position: relative;
  background: #ffffff; border-radius: 18px;
  padding: 16px 14px 14px; display: flex; flex-direction: column; gap: 10px;
  min-height: 132px;
  box-shadow:
    0 0 0 0.5px rgba(0,0,0,0.06),
    0 2px 6px rgba(0,0,0,0.06),
    0 10px 28px rgba(0,0,0,0.11),
    0 24px 48px rgba(0,0,0,0.05);
  transition: box-shadow 0.25s ease, transform 0.25s ease;
}}
.cell:not(.fixed):hover {{
  box-shadow:
    0 0 0 0.5px rgba(0,0,0,0.08),
    0 4px 12px rgba(0,0,0,0.10),
    0 20px 48px rgba(0,0,0,0.17),
    0 40px 72px rgba(0,0,0,0.07);
  transform: translateY(-3px);
}}
.cell.fixed {{ opacity: 0.28; pointer-events: none; }}
.knum {{ font-size: 10px; font-weight: 500; color: #aeaeb2; letter-spacing: 0.04em; }}
.kfunc {{
  font-size: 16px; font-weight: 700; color: #1d1d1f;
  line-height: 1.25; flex: 1; text-align: center; letter-spacing: -0.02em;
}}
input[type=text] {{
  width: 100%; padding: 10px 12px;
  background: #f2f2f7; border: none; border-radius: 10px;
  color: #1d1d1f; font-size: 14px; text-align: center; outline: none;
  font-family: inherit; font-weight: 500;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,0.06);
  transition: background 0.15s ease, box-shadow 0.15s ease;
}}
input[type=text]:focus {{
  background: #fff;
  box-shadow: inset 0 0 0 2px #1d1d1f;
}}
input[type=text]::placeholder {{ color: #c7c7cc; font-weight: 400; }}
.badge-fixed {{
  padding: 9px 12px; background: #f2f2f7; border-radius: 10px;
  color: #c7c7cc; font-size: 11px; text-align: center; font-weight: 600;
  letter-spacing: 0.02em;
}}
.badge {{
  padding: 11px 12px 10px; background: #1d1d1f; border-radius: 12px;
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.22), 0 6px 20px rgba(0,0,0,0.14);
}}
.badge-lbl {{ font-size: 14px; color: #fff; font-weight: 700; letter-spacing: -0.02em; }}
.badge-val {{ font-size: 10px; color: rgba(255,255,255,0.38); font-weight: 500; letter-spacing: 0.02em; }}
.actions {{
  text-align: center; max-width: 680px; margin: 30px auto 56px;
  display: flex; justify-content: center; gap: 10px;
}}
.btn-save, .btn-reset {{
  padding: 13px 34px; border-radius: 980px; font-size: 15px;
  font-weight: 600; cursor: pointer; letter-spacing: -0.01em; font-family: inherit;
  transition: opacity 0.15s ease, transform 0.18s ease, box-shadow 0.18s ease;
}}
.btn-save {{
  background: #1d1d1f; color: #fff; border: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.20), 0 8px 28px rgba(0,0,0,0.14);
}}
.btn-reset {{ background: rgba(0,0,0,0.07); color: #6e6e73; border: none; }}
.btn-save:hover {{
  opacity: 0.84; transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(0,0,0,0.24), 0 14px 36px rgba(0,0,0,0.16);
}}
.btn-reset:hover {{ background: rgba(0,0,0,0.11); color: #1d1d1f; }}
.tray-wrap {{
  max-width: 680px; margin: 0 auto;
  border-top: 1px solid rgba(0,0,0,0.10); padding-top: 36px;
}}
.tray-title {{
  font-size: 11px; color: #6e6e73; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 22px;
}}
.tray {{ display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }}
.card-group {{ display: flex; flex-direction: column; gap: 8px; }}
.card-group-lbl {{
  font-size: 10px; color: #aeaeb2; font-weight: 600;
  letter-spacing: 0.09em; text-transform: uppercase; padding: 0 2px;
}}
.card-group-items {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.card {{
  display: flex; flex-direction: column; align-items: center;
  padding: 10px 16px 9px; background: #fff; border-radius: 12px;
  cursor: grab; user-select: none;
  box-shadow:
    0 1px 3px rgba(0,0,0,0.06),
    0 4px 14px rgba(0,0,0,0.09);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}}
.card:hover {{
  box-shadow:
    0 2px 8px rgba(0,0,0,0.10),
    0 8px 26px rgba(0,0,0,0.13);
  transform: translateY(-2px);
}}
.card:active {{ transform: scale(0.94); cursor: grabbing; }}
.card-lbl {{ font-size: 13px; color: #1d1d1f; font-weight: 600; letter-spacing: -0.01em; }}
.card-val {{ font-size: 10px; color: #aeaeb2; margin-top: 2px; font-weight: 500; }}
.cell.drop-over {{
  box-shadow: 0 0 0 2.5px #1d1d1f, 0 8px 24px rgba(0,0,0,0.18);
  transform: scale(1.03);
}}
.btn-x {{
  position: absolute; top: 9px; right: 9px;
  width: 20px; height: 20px; border-radius: 50%; border: none;
  background: rgba(0,0,0,0.07); color: #6e6e73; font-size: 13px; line-height: 1;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  padding: 0; transition: background 0.15s ease, color 0.15s ease;
}}
.btn-x:hover {{ background: #1d1d1f; color: #fff; }}
/* ── 클릭 선택 모드 ─────────────────────────── */
.card.card-selected {{
  box-shadow:
    0 0 0 2.5px #1d1d1f,
    0 4px 20px rgba(0,0,0,0.18);
  transform: translateY(-3px) scale(1.06);
  cursor: pointer;
}}
.cell.pick-target:not(.fixed) {{
  cursor: pointer;
  box-shadow:
    0 0 0 1.5px rgba(29,29,31,0.20),
    0 2px 6px rgba(0,0,0,0.06),
    0 10px 28px rgba(0,0,0,0.11),
    0 24px 48px rgba(0,0,0,0.05);
}}
.cell.pick-target:not(.fixed):hover {{
  box-shadow:
    0 0 0 2px #1d1d1f,
    0 4px 12px rgba(0,0,0,0.10),
    0 20px 48px rgba(0,0,0,0.17);
  transform: translateY(-2px);
}}
#card-ghost {{
  position: fixed;
  pointer-events: none;
  z-index: 300;
  opacity: 0.78;
  transform: translate(-50%, -50%) rotate(-4deg) scale(1.10);
  box-shadow:
    0 8px 28px rgba(0,0,0,0.22),
    0 20px 48px rgba(0,0,0,0.14);
}}
.layout {{
  display: flex; gap: 24px; max-width: 1000px; margin: 0 auto; align-items: flex-start;
}}
.left-col-wrap {{
  width: 280px; flex-shrink: 0;
  display: flex; flex-direction: column; gap: 12px;
}}
.joy-panel {{
  background: #fff; border-radius: 20px; padding: 24px 20px;
  height: 420px;
  display: flex; flex-direction: column;
  box-shadow:
    0 0 0 0.5px rgba(0,0,0,0.06),
    0 2px 6px rgba(0,0,0,0.06),
    0 10px 28px rgba(0,0,0,0.11),
    0 24px 48px rgba(0,0,0,0.05);
}}
.joy-actions {{
  display: flex; flex-direction: column; gap: 8px;
  height: 132px; justify-content: center;
}}
.joy-actions .btn-save,
.joy-actions .btn-reset {{
  width: 100%; padding: 13px 20px; text-align: center;
}}
.joy-panel-title {{
  font-size: 11px; color: #6e6e73; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0;
}}
.joy-item {{ margin-bottom: 20px; }}
.joy-item:last-of-type {{ margin-bottom: 0; }}
.joy-label {{
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 10px;
}}
.joy-label-name {{
  font-size: 14px; font-weight: 600; color: #1d1d1f; letter-spacing: -0.01em;
}}
.joy-val {{
  font-size: 22px; font-weight: 700; color: #1d1d1f; letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}}
.joy-range-ends {{
  display: flex; justify-content: space-between;
  font-size: 10px; color: #aeaeb2; font-weight: 500; margin-top: 8px;
  letter-spacing: 0.01em;
}}
input[type=range] {{
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 4px; border-radius: 2px;
  background: #e5e5ea; outline: none; cursor: pointer; display: block;
}}
input[type=range]::-webkit-slider-thumb {{
  -webkit-appearance: none;
  width: 24px; height: 24px; border-radius: 50%;
  background: #1d1d1f; cursor: pointer;
  box-shadow: 0 1px 4px rgba(0,0,0,0.30), 0 2px 8px rgba(0,0,0,0.15);
}}
input[type=range]::-moz-range-thumb {{
  width: 24px; height: 24px; border-radius: 50%; border: none;
  background: #1d1d1f; cursor: pointer;
  box-shadow: 0 1px 4px rgba(0,0,0,0.30);
}}
.btn-joy-save {{
  width: 100%; padding: 11px; border-radius: 980px; border: none;
  background: #1d1d1f; color: #fff; font-size: 14px; font-weight: 600;
  cursor: pointer; letter-spacing: -0.01em; font-family: inherit;
  box-shadow: 0 2px 8px rgba(0,0,0,0.20), 0 6px 20px rgba(0,0,0,0.12);
  transition: opacity 0.15s ease, transform 0.18s ease;
}}
.btn-joy-save:hover {{ opacity: 0.84; transform: translateY(-1px); }}
.right-col {{ flex: 1; min-width: 0; }}
.right-col .grid {{ max-width: none; margin: 0 0 18px; }}
/* ── 장식 다이얼 ── */
.dial-wrap {{
  flex: 1;
  display: flex; align-items: center; justify-content: center;
}}
.dial-pedestal {{
  width: 136px; height: 136px; border-radius: 50%;
  background: #ebebf0;
  box-shadow:
    inset 3px 3px 8px rgba(0,0,0,0.13),
    inset -2px -2px 6px rgba(255,255,255,0.88);
  display: flex; align-items: center; justify-content: center;
}}
.dial-base {{
  width: 112px; height: 112px; border-radius: 50%;
  background: #1c1c1e;
  box-shadow:
    3px 5px 16px rgba(0,0,0,0.50),
    0 1px 3px rgba(0,0,0,0.28),
    inset 0 0 0 1.5px rgba(255,255,255,0.06),
    inset 0 1px 3px rgba(255,255,255,0.04);
  display: flex; align-items: center; justify-content: center;
}}
.dial-knob {{
  width: 76px; height: 76px; border-radius: 50%;
  background: radial-gradient(circle at 40% 35%, #3c3c3e, #111113);
  box-shadow:
    2px 4px 11px rgba(0,0,0,0.70),
    -1px -1px 4px rgba(255,255,255,0.05),
    inset 0 1px 2px rgba(255,255,255,0.09),
    inset 0 -2px 5px rgba(0,0,0,0.65);
  display: flex; align-items: flex-start;
  justify-content: center; padding-top: 13px;
}}
.dial-dot {{
  width: 6px; height: 6px; border-radius: 50%;
  background: rgba(255,255,255,0.82);
  box-shadow: 0 0 5px rgba(255,255,255,0.50);
}}
.right-col .tray-wrap {{ max-width: none; }}
@media (max-height: 820px) {{
  body {{ padding: 28px 20px 48px; }}
  h1 {{ font-size: 22px; margin-bottom: 6px; }}
  .sub {{ font-size: 13px; margin-bottom: 22px; }}
  .cell {{ min-height: 104px; padding: 12px 12px 10px; gap: 7px; }}
  .kfunc {{ font-size: 13px; }}
  input[type=text] {{ padding: 7px 10px; font-size: 12px; }}
  .badge {{ padding: 8px 10px 7px; }}
  .badge-lbl {{ font-size: 12px; }}
  .badge-val {{ font-size: 9px; }}
  .joy-item {{ margin-bottom: 14px; }}
  .joy-val {{ font-size: 18px; }}
  .joy-label {{ margin-bottom: 7px; }}
  .tray-wrap {{ padding-top: 24px; }}
  .tray-title {{ margin-bottom: 14px; }}
}}
@media (max-width: 760px) {{
  .layout {{ flex-direction: column; }}
  .left-col-wrap {{ width: 100%; }}
  .right-col .grid {{ max-width: 680px; margin: 0 auto 18px; }}
  .right-col .tray-wrap {{ max-width: 680px; margin: 0 auto; }}
}}
@media (max-width: 520px) {{
  .grid {{ grid-template-columns: repeat(2, 1fr); }}
  .tray {{ gap: 14px; }}
}}
</style>
</head>
<body>
  <h1>천지인 키보드 설정</h1>
  <p class="sub">직접 입력하거나 아래 카드를 드래그 또는 클릭해서 적용하세요</p>
  {banner}
  <div class="layout">
    <div class="left-col-wrap">
    <div class="joy-panel">
      <div class="joy-panel-title">조이스틱 설정</div>
      <div class="dial-wrap">
        <div class="dial-pedestal">
          <div class="dial-base">
            <div class="dial-knob">
              <div class="dial-dot"></div>
            </div>
          </div>
        </div>
      </div>
      <div class="joy-item">
          <div class="joy-label">
            <span class="joy-label-name">속도</span>
            <span class="joy-val" id="ms-val">{joy_ms}</span>
          </div>
          <input type="range" name="mouse_speed" form="mainform" min="1" max="30" step="1"
                 value="{joy_ms}"
                 oninput="document.getElementById('ms-val').textContent=this.value" />
          <div class="joy-range-ends"><span>느림</span><span>빠름</span></div>
        </div>
        <div class="joy-item">
          <div class="joy-label">
            <span class="joy-label-name">우클릭 감지</span>
            <span class="joy-val" id="rch-val">{joy_rch}s</span>
          </div>
          <input type="range" name="right_click_hold" form="mainform" min="0.1" max="2.0" step="0.1"
                 value="{joy_rch}"
                 oninput="document.getElementById('rch-val').textContent=this.value+'s'" />
          <div class="joy-range-ends"><span>짧게</span><span>길게</span></div>
        </div>
    </div>
    <div class="joy-actions">
      <button type="submit" class="btn-save" form="mainform">저장하기</button>
      <button type="submit" class="btn-reset" form="mainform" formaction="/reset">기본값 복원</button>
    </div>
    </div>
    <div class="right-col">
      <form id="mainform" method="POST" action="/save">
        <div class="grid">{cells}</div>
      </form>
      <div class="tray-wrap">
        <div class="tray-title">매크로 카드</div>
        <div class="tray" id="tray">{cards}</div>
      </div>
    </div>
  </div>
  <script>
    // ── 드래그 중 자동 스크롤 ────────────────────
    document.addEventListener("dragover", function(e) {{
      var ZONE = 80, SPEED = 12;
      var y = e.clientY, h = window.innerHeight;
      if (y < ZONE)      window.scrollBy(0, -SPEED * (1 - y / ZONE));
      else if (y > h - ZONE) window.scrollBy(0,  SPEED * (y - (h - ZONE)) / ZONE);
    }});

    // ── 마우스 엣지 스크롤 (조이스틱용) ─────────
    var _edgeSI = null;
    document.addEventListener("mousemove", function(e) {{
      var ZONE = 60;
      var y = e.clientY, h = window.innerHeight;
      if (_edgeSI) {{ clearInterval(_edgeSI); _edgeSI = null; }}
      if (y < ZONE) {{
        var sp = Math.max(2, Math.round((ZONE - y) / ZONE * 12));
        _edgeSI = setInterval(function() {{ window.scrollBy(0, -sp); }}, 16);
      }} else if (y > h - ZONE) {{
        var sp = Math.max(2, Math.round((y - (h - ZONE)) / ZONE * 12));
        _edgeSI = setInterval(function() {{ window.scrollBy(0, sp); }}, 16);
      }}
    }});

    // ── 드래그 / 클릭 선택 상태 ─────────────────
    var _dv = "", _dl = "";
    var _sel = null; // {{ value, label, el }} or null

    document.querySelectorAll(".card").forEach(function(c) {{
      c.setAttribute("draggable", "true");
      c.addEventListener("dragstart", function(e) {{
        clearSel();
        _dv = c.dataset.value;
        _dl = c.querySelector(".card-lbl").textContent;
        e.dataTransfer.effectAllowed = "copy";
      }});
      c.addEventListener("click", function(e) {{
        if (_sel && _sel.el === c) {{ clearSel(); return; }}
        if (_sel) _sel.el.classList.remove("card-selected");
        _sel = {{ value: c.dataset.value, label: c.querySelector(".card-lbl").textContent, el: c }};
        c.classList.add("card-selected");
        createGhost(c, e.clientX, e.clientY);
        document.querySelectorAll(".cell:not(.fixed)").forEach(function(cell) {{
          cell.classList.add("pick-target");
        }});
      }});
    }});

    document.querySelectorAll(".cell:not(.fixed)").forEach(function(cell) {{
      cell.addEventListener("dragover", function(e) {{
        e.preventDefault();
        cell.classList.add("drop-over");
      }});
      cell.addEventListener("dragleave", function() {{
        cell.classList.remove("drop-over");
      }});
      cell.addEventListener("drop", function(e) {{
        e.preventDefault();
        cell.classList.remove("drop-over");
        lockCell(cell, _dv, _dl);
      }});
    }});

    // ── 클릭 선택 → 셀 적용 ──────────────────────
    document.querySelectorAll(".cell:not(.fixed)").forEach(function(cell) {{
      cell.addEventListener("click", function(e) {{
        if (!_sel) return;
        if (e.target.closest(".btn-x")) return;
        lockCell(cell, _sel.value, _sel.label);
        clearSel();
      }});
    }});

    function lockCell(cell, value, label) {{
      var el;
      while ((el = cell.querySelector(".badge,input,.btn-x"))) el.remove();
      var k = cell.dataset.key;
      var badge = document.createElement("div");
      badge.className = "badge";
      badge.innerHTML =
        '<span class="badge-lbl">' + label + "</span>" +
        '<span class="badge-val">' + value + "</span>";
      cell.appendChild(badge);
      var inp = document.createElement("input");
      inp.type = "hidden"; inp.name = "key" + k; inp.value = value;
      cell.appendChild(inp);
      cell.appendChild(makeX());
      cell.classList.add("locked");
    }}

    function unlockCell(cell) {{
      var el;
      while ((el = cell.querySelector(".badge,input,.btn-x"))) el.remove();
      var k = cell.dataset.key;
      var inp = document.createElement("input");
      inp.type = "text"; inp.name = "key" + k; inp.value = "";
      inp.maxLength = 1; inp.autocomplete = "off"; inp.placeholder = "a";
      cell.appendChild(inp);
      cell.classList.remove("locked");
    }}

    function makeX() {{
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "btn-x"; btn.textContent = "×";
      btn.onclick = function() {{ unlockCell(btn.parentElement); }};
      return btn;
    }}

    var _ghost = null;
    function createGhost(cardEl, x, y) {{
      removeGhost();
      var g = cardEl.cloneNode(true);
      g.id = "card-ghost";
      g.removeAttribute("draggable");
      g.style.left = x + "px";
      g.style.top = y + "px";
      document.body.appendChild(g);
      _ghost = g;
    }}
    function removeGhost() {{
      if (_ghost) {{ _ghost.remove(); _ghost = null; }}
    }}
    document.addEventListener("mousemove", function(e) {{
      if (_ghost) {{
        _ghost.style.left = e.clientX + "px";
        _ghost.style.top = e.clientY + "px";
      }}
    }});

    function clearSel() {{
      if (_sel) {{ _sel.el.classList.remove("card-selected"); _sel = null; }}
      document.querySelectorAll(".pick-target").forEach(function(c) {{ c.classList.remove("pick-target"); }});
      removeGhost();
    }}

    document.addEventListener("click", function(e) {{
      if (!_sel) return;
      if (e.target.closest(".card") || e.target.closest(".cell") || e.target.closest("#sel-bar")) return;
      clearSel();
    }});

    document.addEventListener("keydown", function(e) {{
      if (e.key === "Escape" && _sel) clearSel();
    }});

    // ── 조이스틱 패널 높이 동기화 ──────────────────
    function alignJoyPanel() {{
      var cells = Array.from(document.querySelectorAll(".cell"));
      if (cells.length < 16) return;
      var rowH = cells[0].getBoundingClientRect().height;
      var gap = 12;
      document.querySelector(".joy-panel").style.height = (3 * rowH + 2 * gap - 10) + "px";
      document.querySelector(".joy-actions").style.height = rowH + "px";
    }}
    alignJoyPanel();
    window.addEventListener("resize", alignJoyPanel);

    // ── 배너 페이드 아웃 ──────────────────────────
    var b = document.getElementById("banner");
    if (b) {{
      setTimeout(function () {{
        b.style.transition = "opacity 0.6s";
        b.style.opacity = "0";
        setTimeout(function () {{ b.style.display = "none"; }}, 600);
      }}, 8000);
    }}
  </script>

</body>
</html>"""


# ─────────────────────────────────────────────────────────────
# HTTP 핸들러
# ─────────────────────────────────────────────────────────────
class SetterHandler(BaseHTTPRequestHandler):
    def _send_html(self, body, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            query = parse_qs(urlparse(self.path).query)
            if "saved" in query:
                status = "saved"
            elif "reset" in query:
                status = "reset"
            elif "joy_saved" in query:
                status = "joy_saved"
            else:
                status = None
            self._send_html(render_page(load_config(), status=status))
        elif path == "/config.json":
            # 현재 설정을 JSON 으로도 확인 가능(디버그용)
            data = json.dumps(load_config(), ensure_ascii=False, indent=4)
            self._send_html(f"<pre>{html.escape(data)}</pre>")
        else:
            self._send_html("<h1>404 Not Found</h1>", status=404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        # parse_qs는 + 를 공백으로 디코딩. 브라우저가 %2B 대신 + 를 그대로 보낸 경우도
        # 처리하기 위해 리터럴 + 를 먼저 %2B 로 치환한다.
        # 브라우저가 이미 %2B 로 보낸 경우(ctrl+c → ctrl%2Bc)는 %2B 가 없으므로 영향 없음.
        form = parse_qs(raw.replace("+", "%2B"))

        if path == "/save":
            mapping = load_config()
            for i in range(1, TOTAL_KEYS + 1):
                if i == FIXED_KEY_ID:
                    continue
                field = f"key{i}"
                if field in form:
                    mapping[str(i)] = form[field][0]
            joy_data = {
                "mouse_speed":    form.get("mouse_speed",    [str(JOYSTICK_DEFAULTS["mouse_speed"])])[0],
                "right_click_hold": form.get("right_click_hold", [str(JOYSTICK_DEFAULTS["right_click_hold"])])[0],
            }
            try:
                save_joystick_config(joy_data)  # 조이스틱 먼저 → save_config가 머지 읽음
                save_config(mapping)
            except OSError as e:
                self._send_html(f"<h1>저장 실패</h1><p>{html.escape(str(e))}</p>",
                                status=500)
                return
            self._redirect("/?saved=1")
        elif path == "/reset":
            try:
                save_joystick_config(JOYSTICK_DEFAULTS)  # 조이스틱 기본값 먼저
                save_config(DEFAULT_MAPPING)
            except OSError as e:
                self._send_html(f"<h1>복원 실패</h1><p>{html.escape(str(e))}</p>",
                                status=500)
                return
            self._redirect("/?reset=1")
        elif path == "/save_joystick":
            try:
                ms  = float(form.get("mouse_speed",  [str(JOYSTICK_DEFAULTS["mouse_speed"])])[0])
                rch = float(form.get("right_click_hold", [str(JOYSTICK_DEFAULTS["right_click_hold"])])[0])
                save_joystick_config({"mouse_speed": ms, "right_click_hold": rch})
            except (ValueError, OSError) as e:
                self._send_html(f"<h1>저장 실패</h1><p>{html.escape(str(e))}</p>",
                                status=500)
                return
            self._redirect("/?joy_saved=1")
        else:
            self._send_html("<h1>404 Not Found</h1>", status=404)

    def log_message(self, fmt, *args):
        # 접속 로그를 간단히
        print(f"  [접속] {self.address_string()}  {fmt % args}")


def get_local_ip():
    """라즈베리파이의 로컬 IP 추정(표시용)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))   # 실제 전송 안 함, 라우팅만 확인
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    # config 가 없으면 기본값 생성
    load_config()

    ip = get_local_ip()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), SetterHandler)
    print("=" * 55)
    print(" 천지인 키보드 웹 설정 서버 시작")
    print("=" * 55)
    print(f"  노트북/폰 브라우저에서 접속:")
    print(f"     http://{ip}:{PORT}")
    print(f"  (노트북과 같은 와이파이에 연결되어 있어야 합니다)")
    print(f"  종료: Ctrl+C")
    print("=" * 55)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료.")
        server.shutdown()


if __name__ == "__main__":
    main()