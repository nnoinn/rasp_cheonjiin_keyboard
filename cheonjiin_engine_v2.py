#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
천지인(天地人) 한글 조합 오토마타 엔진  v2
- 라즈베리파이 4 기반 16키 키보드용 순수 소프트웨어 엔진
- 외부 라이브러리(pyautogui, gpiozero) 미사용. 표준 라이브러리 + 유니코드 계산만 사용.
- 하드웨어 인터페이스는 v1과 동일하게 engine.press(key) 한 줄만 호출하면 된다.

v2 추가 기능
  [1] 백스페이스(Undo) 자모/stroke 단위 되돌리기
      - 모음 조합 중: 마지막 stroke만 제거 (ㅑ→ㅏ→ㅣ→없음)
      - 자음/받침: 자모 단독으로 하나씩 제거 (겹받침 ㄳ→ㄱ)
  [2] 종성 겹받침 자동 조합 + 도깨비불 분해
      - 받침 ㄱ 뒤에 ㅅ → ㄳ
      - '값' 뒤에 모음 '이' → '갑시' (뒷자음만 다음 초성으로 이동)

[키 매핑]
  모음:  1=ㅣ(人) 2=ㆍ(天) 3=ㅡ(地)
  자음:  5=ㄱ/ㅋ 6=ㄴ/ㄹ 7=ㄷ/ㅌ 8=ㅂ/ㅍ 9=ㅅ/ㅎ 0=ㅈ/ㅊ 4=ㅁ/ㅇ  (0.5s 이내 연타=토글)
  쌍자음: s + 자음키 → ㄲㄸㅃㅆㅉ
  영어:  mode 전환, 10=v↔w, 11=x→y→z→x
  기타:  space=확정/띄기  back=자모 단위 되돌리기  mode=한/영  q=종료
"""

import time

# ─────────────────────────────────────────────────────────────
# 1. 유니코드 한글 조합 테이블
# ─────────────────────────────────────────────────────────────
HANGUL_BASE = 0xAC00

CHOSUNG = [
    'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ',
    'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
]
JUNGSUNG = [
    'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ',
    'ㅘ', 'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ',
    'ㅡ', 'ㅢ', 'ㅣ'
]
JONGSUNG = [
    '', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ',
    'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ',
    'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
]

CHO_IDX = {c: i for i, c in enumerate(CHOSUNG)}
JUNG_IDX = {c: i for i, c in enumerate(JUNGSUNG)}
JONG_IDX = {c: i for i, c in enumerate(JONGSUNG)}


def compose(cho, jung, jong=''):
    """초/중/종성 낱자를 완성형 한 글자로 합친다. 실패 시 None."""
    if cho not in CHO_IDX or jung not in JUNG_IDX:
        return None
    j = JONG_IDX.get(jong, 0)
    code = HANGUL_BASE + (CHO_IDX[cho] * 21 + JUNG_IDX[jung]) * 28 + j
    return chr(code)


# ─────────────────────────────────────────────────────────────
# 2. 겹받침 조합/분해 테이블
#    COMPOUND_JONG[(앞받침, 뒷자음)] = 겹받침   ← 조합
#    SPLIT_JONG[겹받침] = (앞받침, 뒷자음)        ← 도깨비불 분해 (역방향)
# ─────────────────────────────────────────────────────────────
COMPOUND_JONG = {
    ('ㄱ', 'ㅅ'): 'ㄳ',
    ('ㄴ', 'ㅈ'): 'ㄵ',
    ('ㄴ', 'ㅎ'): 'ㄶ',
    ('ㄹ', 'ㄱ'): 'ㄺ',
    ('ㄹ', 'ㅁ'): 'ㄻ',
    ('ㄹ', 'ㅂ'): 'ㄼ',
    ('ㄹ', 'ㅅ'): 'ㄽ',
    ('ㄹ', 'ㅌ'): 'ㄾ',
    ('ㄹ', 'ㅍ'): 'ㄿ',
    ('ㄹ', 'ㅎ'): 'ㅀ',   # 규칙표의 'ㄹ+ㅎ=ㄶ'은 표준상 ㅀ이므로 ㅀ로 둠
    ('ㅂ', 'ㅅ'): 'ㅄ',
}
# 역방향(분해) 테이블 — 도깨비불·Undo에서 사용
SPLIT_JONG = {v: k for k, v in COMPOUND_JONG.items()}


# ─────────────────────────────────────────────────────────────
# 3. 천지인 모음 조합 오토마타 (stroke 누적 + Undo)
# ─────────────────────────────────────────────────────────────
VOWEL_TABLE = {
    'I':    'ㅣ', 'A':    'ㆍ', 'U':    'ㅡ',
    'IA':   'ㅏ', 'IAA':  'ㅑ',
    'AI':   'ㅓ', 'AA':   'ㆍ',  'AAI':  'ㅕ',
    'AU':   'ㅗ', 'AAU':  'ㅛ',
    'UA':   'ㅜ', 'UAA':  'ㅠ',
    'UI':   'ㅢ',
    'IAI':  'ㅐ', 'IAAI': 'ㅒ',
    'AII':  'ㅔ', 'AAII': 'ㅖ',
    'AUI':  'ㅚ', 'AUIA': 'ㅘ', 'AUIAI':'ㅙ',
    'UAI':  'ㅟ', 'UAAI': 'ㅝ', 'UAAII':'ㅞ',
}
KEY_TO_STROKE = {'1': 'I', '2': 'A', '3': 'U'}


class VowelMachine:
    """천지인 모음 stroke 누적 상태 머신. seq 문자열 자체가 곧 Undo 히스토리다."""

    def __init__(self):
        self.seq = ''

    def reset(self):
        self.seq = ''

    def feed(self, stroke):
        """
        stroke 추가 시도.
        반환 (현재모음 or None, 직전에 확정된 모음 or None)
        """
        candidate = self.seq + stroke
        if candidate in VOWEL_TABLE:
            self.seq = candidate
            return VOWEL_TABLE[self.seq], None
        committed = VOWEL_TABLE.get(self.seq)
        if stroke in VOWEL_TABLE:
            self.seq = stroke
            return VOWEL_TABLE[self.seq], committed
        self.seq = ''
        return None, committed

    def undo_stroke(self):
        """
        마지막 stroke 1개 제거.
        반환: True(아직 모음 남음/혹은 비워짐) — 호출부에서 current로 상태 확인.
        """
        if not self.seq:
            return False
        self.seq = self.seq[:-1]
        # seq가 더 이상 유효 모음이 아니면(이론상 거의 없음) 한 칸 더 줄이며 보정
        while self.seq and self.seq not in VOWEL_TABLE:
            self.seq = self.seq[:-1]
        return True

    @property
    def current(self):
        return VOWEL_TABLE.get(self.seq)


# ─────────────────────────────────────────────────────────────
# 4. 자음 토글 / 쌍자음 / 영어 순환 테이블
# ─────────────────────────────────────────────────────────────
CONSONANT_TOGGLE = {
    '5': ['ㄱ', 'ㅋ'], '6': ['ㄴ', 'ㄹ'], '7': ['ㄷ', 'ㅌ'],
    '8': ['ㅂ', 'ㅍ'], '9': ['ㅅ', 'ㅎ'], '0': ['ㅈ', 'ㅊ'], '4': ['ㅇ', 'ㅁ'],
}
DOUBLE_CONSONANT = {'5': 'ㄲ', '7': 'ㄸ', '8': 'ㅃ', '9': 'ㅆ', '0': 'ㅉ'}
DOUBLE_TOGGLE_THRESHOLD = 1.0

ENGLISH_CYCLE = {
    '1': ['a', 'b', 'c'],
    '2': ['d', 'e', 'f'],
    '3': ['g', 'h', 'i'],
    '5': ['j', 'k', 'l'],
    '6': ['m', 'n', 'o'],
    '7': ['p', 'q', 'r'],
    '8': ['s', 't', 'u'],
    '9': ['v', 'w'],
    '0': ['x', 'y', 'z'],
    '4': ['.', ',', '?', '!'],
}


# ─────────────────────────────────────────────────────────────
# 5. 한글 음절 조립기 (초/중/종성 + 겹받침 + 자모 단위 Undo)
# ─────────────────────────────────────────────────────────────
class HangulComposer:
    """
    조립 중인 한 음절 상태 관리.
    Undo를 위해 '조립 이벤트'를 스택(undo_stack)에 기록한다.
    이벤트 종류:
      ('cho', 자음)             초성 채움
      ('jung', stroke)          모음 stroke 추가 (모음 머신 되돌림으로 처리)
      ('jong', 자음)            홑받침 채움
      ('jong_compound', 뒷자음) 겹받침으로 승급 (앞받침 보존)
    """

    def __init__(self):
        self.cho = ''
        self.jung = ''
        self.jong = ''
        self.vm = VowelMachine()
        self.undo_stack = []   # 자모 단위 Undo 히스토리

    def reset(self):
        self.cho = ''
        self.jung = ''
        self.jong = ''
        self.vm.reset()
        self.undo_stack = []

    def is_empty(self):
        return not (self.cho or self.jung or self.jong)

    def render(self):
        if self.cho and self.jung:
            full = compose(self.cho, self.jung, self.jong)
            if full:
                return full
            return (compose(self.cho, self.jung) or '') + self.jong
        if self.cho:
            return self.cho
        if self.jung:
            return self.jung
        return ''

    # ── 자음 입력 ──────────────────────────────────────────
    def input_consonant(self, jaeum):
        """자음 한 개 입력. 배출된 글자 리스트 반환."""
        flushed = []

        if not self.cho and not self.jung:
            self.cho = jaeum
            self.undo_stack.append(('cho', jaeum))

        elif self.cho and not self.jung:
            # 초성만 있는데 또 자음 → 앞 자음 배출, 새 초성
            flushed.append(self.cho)
            self.reset()
            self.cho = jaeum
            self.undo_stack.append(('cho', jaeum))

        elif not self.cho and self.jung:
            # 초성 없이 모음만 있는데 자음 → 앞 모음 배출, 새 초성 시작
            flushed.append(self.jung)
            self.reset()
            self.cho = jaeum
            self.undo_stack.append(('cho', jaeum))

        elif self.cho and self.jung:
            if not self.jong:
                # 종성 자리 채우기
                if jaeum in JONG_IDX:
                    self.jong = jaeum
                    self.vm.reset()
                    self.undo_stack.append(('jong', jaeum))
                else:
                    flushed.append(self.render())
                    self.reset()
                    self.cho = jaeum
                    self.undo_stack.append(('cho', jaeum))
            else:
                # 이미 받침 있음 → 겹받침 승급 시도
                pair = (self.jong, jaeum)
                if pair in COMPOUND_JONG:
                    self.jong = COMPOUND_JONG[pair]
                    self.undo_stack.append(('jong_compound', jaeum))
                else:
                    # 겹받침 불가 → 현재 글자 확정, 새 초성
                    flushed.append(self.render())
                    self.reset()
                    self.cho = jaeum
                    self.undo_stack.append(('cho', jaeum))
        return flushed

    # ── 모음 입력 ──────────────────────────────────────────
    def input_vowel_stroke(self, stroke):
        """천지인 모음 stroke 입력. 배출된 글자 리스트 반환."""
        flushed = []

        # 받침이 있는 상태에서 모음 → 도깨비불
        if self.cho and self.jung and self.jong:
            moving = self.jong
            # 겹받침이면 뒷자음만 이동, 앞받침은 잔류
            if moving in SPLIT_JONG:
                front, back = SPLIT_JONG[moving]
                self.jong = front
                flushed.append(self.render())   # 앞받침만 남긴 글자 확정
                self.reset()
                self.cho = back                  # 뒷자음이 새 초성
            else:
                self.jong = ''
                flushed.append(self.render())    # 받침 없는 글자 확정
                self.reset()
                self.cho = moving                # 받침이 새 초성

            cur, _ = self.vm.feed(stroke)
            if cur:
                self.jung = cur
            self.undo_stack.append(('cho', self.cho))
            self.undo_stack.append(('jung', stroke))
            return flushed

        cur, committed = self.vm.feed(stroke)

        if committed and cur:
            # 모음 머신이 새 모음으로 넘어감 → 이전 음절 확정
            if self.cho:
                self.jung = committed
                flushed.append(self.render())
                self.reset()
                self.jung = cur
            else:
                if committed != 'ㆍ':    # ㆍ는 경유지, Windows 미전송 → committed에 넣지 않음
                    flushed.append(committed)
                self.jung = cur
            self.undo_stack.append(('jung', stroke))
        else:
            if cur:
                self.jung = cur
            self.undo_stack.append(('jung', stroke))
        return flushed

    # ── 자모 단위 Undo ─────────────────────────────────────
    def undo(self):
        """
        조립 중인 음절에서 자모/stroke 하나를 되돌린다.
        반환: True = 음절 내부에서 처리됨, False = 더 되돌릴 게 없음(상위에서 확정문자 삭제).
        """
        if not self.undo_stack:
            return False

        event = self.undo_stack[-1]
        kind = event[0]

        if kind == 'jung':
            # 모음 머신에서 마지막 stroke 제거
            # vm.undo_stroke()가 False(seq 이미 빈 팬텀)이면 그대로 False 전달 →
            # _backspace()가 committed 처리하도록 위임
            undone = self.vm.undo_stroke()
            self.undo_stack.pop()
            if self.vm.current:
                self.jung = self.vm.current
            else:
                self.jung = ''
            return undone

        if kind == 'jong_compound':
            # 겹받침 → 앞받침으로 되돌림
            if self.jong in SPLIT_JONG:
                front, _ = SPLIT_JONG[self.jong]
                self.jong = front
            self.undo_stack.pop()
            return True

        if kind == 'jong':
            self.jong = ''
            self.undo_stack.pop()
            return True

        if kind == 'cho':
            self.cho = ''
            self.undo_stack.pop()
            return True

        return False

    def flush(self):
        out = self.render()
        self.reset()
        return out


# ─────────────────────────────────────────────────────────────
# 6. 통합 엔진 (키 → 엔진). 하드웨어는 engine.press(key)만 호출.
# ─────────────────────────────────────────────────────────────
class CheonjiinEngine:
    def __init__(self):
        self.composer = HangulComposer()
        self.committed = ''
        self.mode = 'KO'

        self._last_key = None
        self._last_time = 0.0
        self._toggle_idx = 0
        self._shift_pending = False

        self._en_last_key = None
        self._en_cycle_idx = 0

    def press(self, key):
        key = key.strip()
        now = time.monotonic()

        if key == 'mode':
            self._commit_current()
            self.mode = 'EN' if self.mode == 'KO' else 'KO'
            self._reset_transient()
            return
        if key == 'back':
            self._backspace()
            return
        if key == 'space':
            if not self.composer.is_empty():
                self._commit_current()
            else:
                self.committed += ' '
            self._reset_transient()
            return
        if key == 's':
            self._shift_pending = True
            return

        if self.mode == 'EN':
            self._handle_english(key, now)
        else:
            self._handle_korean(key, now)

    # ── 한글 ──────────────────────────────────────────────
    def _handle_korean(self, key, now):
        if key in KEY_TO_STROKE:
            self._shift_pending = False
            self._last_key = None
            flushed = self.composer.input_vowel_stroke(KEY_TO_STROKE[key])
            self.committed += ''.join(flushed)
            return

        if key in CONSONANT_TOGGLE:
            if self._shift_pending and key in DOUBLE_CONSONANT:
                self._shift_pending = False
                jaeum = DOUBLE_CONSONANT[key]
                self.committed += ''.join(self.composer.input_consonant(jaeum))
                self._last_key = None
                return
            self._shift_pending = False

            options = CONSONANT_TOGGLE[key]
            if (self._last_key == key
                    and (now - self._last_time) <= DOUBLE_TOGGLE_THRESHOLD):
                self._toggle_idx = (self._toggle_idx + 1) % len(options)
                self._retoggle_last_consonant(options[self._toggle_idx])
            else:
                self._toggle_idx = 0
                self.committed += ''.join(
                    self.composer.input_consonant(options[0]))
            self._last_key = key
            self._last_time = now
            return

    def _retoggle_last_consonant(self, new_jaeum):
        c = self.composer
        if c.jong:
            # 겹받침이면 앞받침은 두고 뒷자음만 교체하기는 복잡 → 단순화: 홑받침일 때만 교체
            if c.jong in SPLIT_JONG:
                front, _ = SPLIT_JONG[c.jong]
                pair = (front, new_jaeum)
                if pair in COMPOUND_JONG:
                    c.jong = COMPOUND_JONG[pair]
            elif new_jaeum in JONG_IDX:
                c.jong = new_jaeum
        elif c.cho and not c.jung:
            c.cho = new_jaeum
        elif c.cho and c.jung and not c.jong:
            c.cho = new_jaeum

    # ── 영어 ──────────────────────────────────────────────
    def _handle_english(self, key, now):
        self._commit_current()
        if key in ENGLISH_CYCLE:
            cycle = ENGLISH_CYCLE[key]
            if (self._en_last_key == key
                    and (now - self._last_time) <= DOUBLE_TOGGLE_THRESHOLD):
                self._en_cycle_idx = (self._en_cycle_idx + 1) % len(cycle)
                ch = cycle[self._en_cycle_idx]
                if self._shift_pending:
                    ch = ch.upper()
                self.committed = self.committed[:-1] + ch
            else:
                self._en_cycle_idx = 0
                ch = cycle[0]
                if self._shift_pending:
                    ch = ch.upper()
                self.committed += ch
            self._shift_pending = False
            self._en_last_key = key
            self._last_time = now
        else:
            ch = key.upper() if self._shift_pending else key
            self._shift_pending = False
            self.committed += ch
            self._en_last_key = None

    # ── 보조 ──────────────────────────────────────────────
    def _commit_current(self):
        if not self.composer.is_empty():
            self.committed += self.composer.flush()

    def _reset_transient(self):
        self.composer.reset()
        self._last_key = None
        self._en_last_key = None
        self._shift_pending = False
        self._toggle_idx = 0
        self._en_cycle_idx = 0

    def _backspace(self):
        """자모/stroke 단위 Undo. 음절이 비면 확정 문자열 1글자 삭제."""
        if self.composer.undo():
            self._last_key = None
            return
        if self.committed:
            self.committed = self.committed[:-1]
        self._last_key = None
        self._en_last_key = None

    def display(self):
        return self.committed + self.composer.render()


# ─────────────────────────────────────────────────────────────
# 7. 터미널 루프
# ─────────────────────────────────────────────────────────────
HELP = """
─────────────────────────────────────────────
 천지인 키보드 엔진 v2 (터미널 시뮬레이터)
─────────────────────────────────────────────
 모음 :  1=ㅣ  2=ㆍ  3=ㅡ      (1 2 → ㅏ, 1 2 2 → ㅑ)
 자음 :  5=ㄱ/ㅋ 6=ㄴ/ㄹ 7=ㄷ/ㅌ 8=ㅂ/ㅍ 9=ㅅ/ㅎ 0=ㅈ/ㅊ 4=ㅁ/ㅇ
         (0.5초 이내 같은 키 = 토글)
 쌍자음:  s 누른 뒤 자음키 (s 5 → ㄲ)
 겹받침:  받침 자리에서 자음 2개 연속 (예: ...ㄱ 9 → ㄳ)
 영어 :  mode 로 전환, 10=v/w, 11=x/y/z 순환
 Undo :  back = 자모/stroke 하나씩 되돌리기 (ㅑ→ㅏ→ㅣ, ㄳ→ㄱ)
 기타 :  space=띄기  mode=한/영  q=종료
─────────────────────────────────────────────
 키를 공백으로 구분해 한 줄에 여러 개 입력 가능. 예) 5 1 2
─────────────────────────────────────────────
"""


def run_terminal():
    engine = CheonjiinEngine()
    print(HELP)
    while True:
        try:
            line = input(f"[{engine.mode}] 키 입력> ")
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break
        if line.strip() == 'q':
            print("종료합니다.")
            break
        for tok in line.split():
            if tok == 'q':
                print("종료합니다.")
                return
            engine.press(tok)
        print("  화면 ▶", engine.display())


# ─────────────────────────────────────────────────────────────
# 8. 자동 검증 데모
# ─────────────────────────────────────────────────────────────
def demo():
    print("=== v2 자동 검증 데모 ===\n")

    # [Undo] ㅑ → back → ㅏ → back → ㅣ → back → (빈)
    print("--- [1] 모음 stroke 단위 Undo ---")
    e = CheonjiinEngine()
    for k in ['1', '2', '2']:
        e.press(k)
    print("1 2 2          ->", repr(e.display()), "(기대: ㅑ)")
    e.press('back')
    print("  back         ->", repr(e.display()), "(기대: ㅏ)")
    e.press('back')
    print("  back         ->", repr(e.display()), "(기대: ㅣ)")
    e.press('back')
    print("  back         ->", repr(e.display()), "(기대: 빈)")

    # [Undo] 자음/받침 단위
    print("\n--- [1] 자음·받침 단위 Undo ---")
    e = CheonjiinEngine()
    for k in ['5', '1', '2', '6']:   # 가 + 받침 ㄴ = 간
        e.press(k)
    print("5 1 2 6        ->", repr(e.display()), "(기대: 간)")
    e.press('back')
    print("  back         ->", repr(e.display()), "(기대: 가)")
    e.press('back')
    print("  back         ->", repr(e.display()), "(기대: ㄱ  ※ㅏ stroke 되돌림)")

    # [겹받침] ㄱ + ㅅ = ㄳ  → '갃'
    print("\n--- [2] 겹받침 자동 조합 ---")
    e = CheonjiinEngine()
    for k in ['5', '1', '2', '5', '9']:   # ㄱㅏ + ㄱ받침 + ㅅ → ㄳ
        e.press(k)
    print("5 1 2 5 9      ->", repr(e.display()), "(기대: 갃)")

    # 겹받침 Undo: 갃 → back → 각
    e.press('back')
    print("  back         ->", repr(e.display()), "(기대: 각)")

    # [도깨비불] '값' + 모음 '이' → '갑시'
    print("\n--- [2] 겹받침 도깨비불 (값+이=갑시) ---")
    e = CheonjiinEngine()
    # 값 = ㄱ(5) ㅏ(1,2) ㅂ받침(8) ㅅ(9→겹받침ㅄ)
    for k in ['5', '1', '2', '8', '9']:
        e.press(k)
    print("값 조립        ->", repr(e.display()), "(기대: 값)")
    # 이 = ㅣ(1)  → 도깨비불로 ㅅ이 다음 초성
    e.press('1')
    print("  +1(ㅣ)       ->", repr(e.display()), "(기대: 갑시)")

    # 단순 받침 도깨비불 확인: 간 + ㅣ → 가니
    print("\n--- [2] 홑받침 도깨비불 (간+이=가니) ---")
    e = CheonjiinEngine()
    for k in ['5', '1', '2', '6', '1']:   # 간 + ㅣ
        e.press(k)
    print("5 1 2 6 1      ->", repr(e.display()), "(기대: 가니)")

    # [회귀] 기존 규칙 정상 동작 재확인
    print("\n--- [회귀] 기존 규칙 ---")
    e = CheonjiinEngine(); e.press('5'); e.press('5')
    print("5 5(빠름)      ->", repr(e.display()), "(기대: ㅋ)")
    e = CheonjiinEngine(); e.press('s'); e.press('5')
    print("s 5            ->", repr(e.display()), "(기대: ㄲ)")
    e = CheonjiinEngine(); e.press('mode'); e.press('11'); e.press('11')
    print("EN 11 11       ->", repr(e.display()), "(기대: y)")

    print("\n=== 데모 끝 ===\n")


if __name__ == '__main__':
    demo()
    run_terminal()