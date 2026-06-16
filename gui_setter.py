#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SDI 키 커스텀 프로그램  (라즈베리파이 16키 커스텀 모드 설정 툴) — 최종본
- 표준 라이브러리 tkinter / json 만 사용.
- 4x4(16키) 레이아웃. 16번 키는 '모드 전환(고정)'으로 비활성화.
- config.json 을 읽어 매핑 표시, 없으면 기본값으로 자동 생성.
- 1~15번 클릭 시 매핑 입력 팝업, [저장하기]로 config.json 갱신.

[v3 보완]
- 자주 쓰는 매크로 프리셋 드롭다운 대거 추가.
- 모든 매핑값을 소문자 'modifier+key' 형태로 정규화하여 저장.
  → 펌웨어에서  parts = value.split('+');  pyautogui.hotkey(*parts)  로 바로 사용 가능.

실행:  python3 gui_setter.py   (tkinter 필요: sudo apt install python3-tk)
"""

import json
import os
import tkinter as tk
from tkinter import messagebox

# ─────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

GRID_ROWS = 4
GRID_COLS = 4
TOTAL_KEYS = GRID_ROWS * GRID_COLS          # 16
FIXED_KEY_ID = TOTAL_KEYS                    # 16번 = 고정 모드 전환 키
FIXED_KEY_LABEL = "MODE\n(고정)"
FIXED_VALUE = "MODE_SWITCH"                  # 고정 키는 정규화 예외

# ─────────────────────────────────────────────────────────────
# 키 정규화 규칙
#  - 구분자 +, -, _, 공백 → 모두 '+' 로 통일
#  - 전부 소문자화
#  - modifier 별칭을 표준 토큰으로 치환 (control→ctrl, command/cmd→meta 등)
#  - modifier 를 정해진 순서(ctrl, shift, alt, meta)로 정렬하여 일관성 확보
# ─────────────────────────────────────────────────────────────
MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl", "^": "ctrl",
    "shift": "shift", "shft": "shift",
    "alt": "alt", "option": "alt", "opt": "alt",
    "meta": "meta", "cmd": "meta", "command": "meta",
    "win": "meta", "super": "meta",
}
MODIFIER_ORDER = ["ctrl", "shift", "alt", "meta"]

# 단일 키 이름 별칭 표준화 (선택적 — 흔한 표기 흡수)
KEY_ALIASES = {
    "esc": "esc", "escape": "esc",
    "return": "enter", "enter": "enter",
    "del": "delete", "delete": "delete",
    "bksp": "backspace", "backspace": "backspace",
    "spacebar": "space", "space": "space",
    "pgup": "pageup", "pgdn": "pagedown",
}


def normalize_key(value: str) -> str:
    """
    사용자 입력(자유 형식)을 'modifier+key' 표준형으로 정규화한다.
    예) 'Ctrl + C' -> 'ctrl+c',  'CONTROL-c' -> 'ctrl+c',
        'shift A'  -> 'shift+a',  'ALT+F4' -> 'alt+f4'
    빈 문자열이면 빈 문자열 반환(상위에서 거름).
    """
    if value is None:
        return ""
    s = value.strip()
    if not s:
        return ""
    if s == FIXED_VALUE:        # 고정 키 값은 그대로 둠
        return FIXED_VALUE

    # 구분자 통일: -, _, 공백 → +  (단, '^' 접두 ctrl 표기는 별도 처리됨)
    for sep in ("-", "_", " "):
        s = s.replace(sep, "+")
    # 연속 + 정리
    while "++" in s:
        s = s.replace("++", "+")
    s = s.strip("+").lower()
    if not s:
        return ""

    tokens = [t for t in s.split("+") if t]
    if not tokens:
        return ""

    mods = []
    keys = []
    for t in tokens:
        if t in MODIFIER_ALIASES:
            std = MODIFIER_ALIASES[t]
            if std not in mods:
                mods.append(std)
        else:
            keys.append(KEY_ALIASES.get(t, t))

    # modifier 정렬 (정의된 순서대로)
    mods_sorted = [m for m in MODIFIER_ORDER if m in mods]

    # key 가 없고 modifier 만 입력된 경우 → 그 자체를 키로 취급(예: 'ctrl' 단독)
    if not keys:
        return "+".join(mods_sorted) if mods_sorted else tokens[-1]

    # 일반적으로 마지막 비modifier 토큰 하나만 실제 키로 사용
    main_key = keys[-1]
    return "+".join(mods_sorted + [main_key])


# 기본 매핑값 (정규화된 형태로 저장)
DEFAULT_MAPPING = {
    "1": "1", "2": "2", "3": "3", "4": "4",
    "5": "5", "6": "6", "7": "7", "8": "8",
    "9": "9", "10": "0", "11": "a", "12": "b",
    "13": "ctrl+c", "14": "ctrl+v", "15": "backspace",
    "16": FIXED_VALUE,
}

# 팝업 드롭다운 프리셋: (표시 라벨, 저장될 값)
PRESET_ITEMS = [
    ("복사  (ctrl+c)",       "ctrl+c"),
    ("붙여넣기  (ctrl+v)",   "ctrl+v"),
    ("잘라내기  (ctrl+x)",   "ctrl+x"),
    ("실행취소  (ctrl+z)",   "ctrl+z"),
    ("다시실행  (ctrl+y)",   "ctrl+y"),
    ("전체선택  (ctrl+a)",   "ctrl+a"),
    ("저장  (ctrl+s)",       "ctrl+s"),
    ("찾기  (ctrl+f)",       "ctrl+f"),
    ("창 닫기  (alt+f4)",    "alt+f4"),
    ("──────────",          None),
    ("Space",                "space"),
    ("Enter",                "enter"),
    ("Backspace",            "backspace"),
    ("Tab",                  "tab"),
    ("Esc",                  "esc"),
    ("방향키 ↑",             "up"),
    ("방향키 ↓",             "down"),
    ("방향키 ←",             "left"),
    ("방향키 →",             "right"),
]

# ── 다크 테마 색상 ────────────────────────────────────────────
COLOR_BG       = "#1e1e1e"
COLOR_PANEL    = "#2a2a2a"
COLOR_KEY      = "#3a3a3a"
COLOR_KEY_ACT  = "#505050"
COLOR_FIXED    = "#262626"
COLOR_ACCENT   = "#4a9eff"
COLOR_TEXT     = "#e6e6e6"
COLOR_SUBTEXT  = "#9a9a9a"
COLOR_ENTRY_BG = "#333333"


# ─────────────────────────────────────────────────────────────
# config.json 입출력
# ─────────────────────────────────────────────────────────────
def load_config():
    """config.json 로드. 없거나 손상 시 기본값 생성 후 반환. 로드값도 정규화."""
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
    """매핑을 정규화하여 config.json 으로 저장(1~16 순서, indent=4)."""
    out = {}
    for i in range(1, TOTAL_KEYS + 1):
        key = str(i)
        if key == str(FIXED_KEY_ID):
            out[key] = FIXED_VALUE
        else:
            out[key] = normalize_key(str(mapping.get(key, "")))
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)


# ─────────────────────────────────────────────────────────────
# 매핑 입력 팝업 (모달)
# ─────────────────────────────────────────────────────────────
class MappingDialog(tk.Toplevel):
    def __init__(self, parent, key_id, current_value):
        super().__init__(parent)
        self.result = None
        self.key_id = key_id

        self.title(f"{key_id}번 키 매핑")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.geometry("340x320")

        tk.Label(self, text=f"{key_id}번 버튼에 매핑할 키", bg=COLOR_BG,
                 fg=COLOR_TEXT, font=("Helvetica", 12, "bold")).pack(pady=(16, 4))
        tk.Label(self, text="직접 입력하거나 아래 프리셋에서 선택하세요\n"
                            "(예: a, space, ctrl+c, shift+a, alt+f4)",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT,
                 font=("Helvetica", 9)).pack(pady=(0, 8))

        self.var = tk.StringVar(value=current_value)
        entry = tk.Entry(self, textvariable=self.var, font=("Consolas", 12),
                         bg=COLOR_ENTRY_BG, fg=COLOR_TEXT,
                         insertbackground=COLOR_TEXT, relief="flat",
                         justify="center")
        entry.pack(fill="x", padx=20, pady=(0, 6), ipady=6)
        entry.focus_set()
        entry.select_range(0, tk.END)

        # 정규화 미리보기
        self.preview = tk.Label(self, text="", bg=COLOR_BG, fg=COLOR_ACCENT,
                                font=("Consolas", 10))
        self.preview.pack(pady=(0, 6))
        self.var.trace_add("write", lambda *a: self._update_preview())
        self._update_preview()

        # 프리셋 드롭다운
        labels = [lbl for lbl, _ in PRESET_ITEMS]
        self._label_to_value = {lbl: val for lbl, val in PRESET_ITEMS}
        preset_var = tk.StringVar(value="프리셋 선택…")
        preset = tk.OptionMenu(self, preset_var, *labels,
                               command=self._on_preset)
        preset.config(bg=COLOR_KEY, fg=COLOR_TEXT, activebackground=COLOR_KEY_ACT,
                      activeforeground=COLOR_TEXT, relief="flat",
                      highlightthickness=0, font=("Helvetica", 10))
        preset["menu"].config(bg=COLOR_PANEL, fg=COLOR_TEXT,
                              activebackground=COLOR_ACCENT)
        preset.pack(padx=20, fill="x")

        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.pack(side="bottom", pady=16)
        tk.Button(btn_frame, text="확인", width=10, command=self._on_ok,
                  bg=COLOR_ACCENT, fg="#ffffff", relief="flat",
                  activebackground="#3a8eef",
                  font=("Helvetica", 10, "bold")).pack(side="left", padx=6)
        tk.Button(btn_frame, text="취소", width=10, command=self._on_cancel,
                  bg=COLOR_KEY, fg=COLOR_TEXT, relief="flat",
                  activebackground=COLOR_KEY_ACT,
                  font=("Helvetica", 10)).pack(side="left", padx=6)

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _update_preview(self):
        norm = normalize_key(self.var.get())
        self.preview.config(text=f"저장될 값:  {norm}" if norm else "")

    def _on_preset(self, label):
        value = self._label_to_value.get(label)
        if value is None:   # 구분선 선택 무시
            return
        self.var.set(value)

    def _on_ok(self):
        norm = normalize_key(self.var.get())
        if not norm:
            messagebox.showwarning("입력 필요", "매핑할 키 이름을 입력하세요.",
                                   parent=self)
            return
        self.result = norm
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


# ─────────────────────────────────────────────────────────────
# 메인 애플리케이션
# ─────────────────────────────────────────────────────────────
class KeySetterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SDI 키 커스텀 설정")
        self.configure(bg=COLOR_BG)
        self.geometry("400x500")
        self.resizable(False, False)

        self.mapping = load_config()
        self.buttons = {}

        self._build_header()
        self._build_grid()
        self._build_footer()
        self._refresh_buttons()

    def _build_header(self):
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill="x", pady=(14, 6))
        tk.Label(header, text="키 커스텀 모드 설정", bg=COLOR_BG, fg=COLOR_TEXT,
                 font=("Helvetica", 15, "bold")).pack()
        tk.Label(header, text="버튼을 클릭해 매핑을 수정하세요  ·  16번은 고정 키",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Helvetica", 9)).pack(pady=(2, 0))

    def _build_grid(self):
        grid = tk.Frame(self, bg=COLOR_PANEL, padx=12, pady=12)
        grid.pack(padx=16, pady=10)
        for r in range(GRID_ROWS):
            grid.rowconfigure(r, weight=1)
            for c in range(GRID_COLS):
                grid.columnconfigure(c, weight=1)
                key_id = r * GRID_COLS + c + 1
                if key_id == FIXED_KEY_ID:
                    btn = tk.Button(grid, text=f"{key_id}\n{FIXED_KEY_LABEL}",
                                    width=8, height=3, state="disabled",
                                    bg=COLOR_FIXED, fg=COLOR_SUBTEXT,
                                    disabledforeground=COLOR_SUBTEXT,
                                    relief="flat", font=("Helvetica", 9, "bold"))
                else:
                    btn = tk.Button(grid, width=8, height=3, bg=COLOR_KEY,
                                    fg=COLOR_TEXT, activebackground=COLOR_KEY_ACT,
                                    activeforeground=COLOR_TEXT, relief="flat",
                                    font=("Helvetica", 9),
                                    command=lambda k=key_id: self._on_key_click(k))
                    btn.bind("<Enter>", lambda e, b=btn: b.config(bg=COLOR_KEY_ACT))
                    btn.bind("<Leave>", lambda e, b=btn: b.config(bg=COLOR_KEY))
                btn.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
                self.buttons[key_id] = btn

    def _build_footer(self):
        footer = tk.Frame(self, bg=COLOR_BG)
        footer.pack(side="bottom", fill="x", pady=14, padx=16)
        self.status = tk.Label(footer, text="", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                               font=("Helvetica", 9))
        self.status.pack(side="top", pady=(0, 6))
        btn_row = tk.Frame(footer, bg=COLOR_BG)
        btn_row.pack()
        tk.Button(btn_row, text="기본값 복원", width=12, command=self._on_reset,
                  bg=COLOR_KEY, fg=COLOR_TEXT, activebackground=COLOR_KEY_ACT,
                  relief="flat", font=("Helvetica", 10)).pack(side="left", padx=6)
        tk.Button(btn_row, text="저장하기", width=14, command=self._on_save,
                  bg=COLOR_ACCENT, fg="#ffffff", activebackground="#3a8eef",
                  relief="flat", font=("Helvetica", 10, "bold")).pack(side="left", padx=6)

    def _refresh_buttons(self):
        for key_id, btn in self.buttons.items():
            if key_id == FIXED_KEY_ID:
                continue
            value = self.mapping.get(str(key_id), "")
            btn.config(text=f"{key_id}\n[ {value} ]")

    def _on_key_click(self, key_id):
        current = self.mapping.get(str(key_id), "")
        dialog = MappingDialog(self, key_id, current)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.mapping[str(key_id)] = dialog.result
            self._refresh_buttons()
            self.status.config(text=f"{key_id}번 -> '{dialog.result}' (저장 전)")

    def _on_save(self):
        try:
            save_config(self.mapping)
            self.mapping = load_config()   # 저장된 정규화 결과를 다시 반영
            self._refresh_buttons()
        except OSError as e:
            messagebox.showerror("저장 실패", f"파일 저장 중 오류:\n{e}", parent=self)
            return
        self.status.config(text=f"저장 완료 -> {os.path.basename(CONFIG_PATH)}")
        messagebox.showinfo("저장 완료",
                            f"매핑이 저장되었습니다.\n{CONFIG_PATH}", parent=self)

    def _on_reset(self):
        if messagebox.askyesno("기본값 복원",
                               "모든 매핑을 기본값으로 되돌릴까요?\n"
                               "(저장하기 전까지는 파일에 반영되지 않습니다)",
                               parent=self):
            self.mapping = dict(DEFAULT_MAPPING)
            self._refresh_buttons()
            self.status.config(text="기본값으로 복원됨 (저장 전)")


def main():
    app = KeySetterApp()
    app.mainloop()


if __name__ == "__main__":
    main()