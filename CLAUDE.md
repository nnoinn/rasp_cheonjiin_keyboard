# 천지인 16키 USB HID 키보드 프로젝트

## 프로젝트 개요
- 라즈베리파이를 USB HID 키보드로 동작시켜, 16키 천지인 배열로 한글을 입력하는 펌웨어.
- 라즈베리파이 내부에서 천지인 자모를 조합하고, **두벌식 자모 키(QWERTY)로 변환해 노트북에 전송** → 윈도우 기본 한글 IME가 실시간 조합한다.
- 아래아(ㆍ)는 모음을 만드는 재료일 뿐이며, **노트북으로 보내지 않는다.** 아래아 경유 구간(ㅕ·ㅛ 등 조합 중)에는 윈도우 화면이 잠시 멈춰 보이는 것이 정상.
- systemd 서비스(cheonjiin.service)로 부팅 시 자동 실행 완료.

## 파일 구조 (프로젝트 루트: ~/Desktop/Proj)
- `cheonjiin_engine_v2.py` — 천지인 조합 오토마타 엔진 (자모 → 완성 한글)
- `main.py` — HID 전송, 스위치 입력 처리, 모드 전환, 타이밍 등 메인 로직
- `config.json`, `gui_setter.py`, `web_setter.py` — 설정 관련
- `usb_gadget_init.sh` — USB 가젯 초기화
- `test_*.py` — 각종 하드웨어/입력 테스트 스크립트

## 작업 규칙 (반드시 지킬 것)
- `cheonjiin_engine_v2.py`, `main.py`, `web_setter.py` **세 파일만** 수정한다.
- **새 파일을 임의로 만들지 않는다.** (테스트가 필요하면 기존 test_*.py 활용하거나 일회성 실행)
- 함수/클래스 구조를 바꾸는 큰 변경은 **먼저 설명하고 확인받는다.**
- 한 번에 **2~3개 문제씩(묶음 단위)만** 고치고, 그때마다 멈춰서 검증 결과를 보고한다.
- **코드 검증(pytest/시뮬레이션) 통과 ≠ 실기 통과.** 반드시 라즈베리파이에서 직접 눌러 확인한다. 코드상 PASS여도 실기에서 다르게 동작할 수 있다.

## 모음 입력 시퀀스 (확정 — 실기 통과 기준)
I=ㅣ, A=아래아(ㆍ), U=ㅡ 로 표기. 아래 모든 시퀀스는 코드+실기 검증 완료.

### 단모음
- ㅣ=`I`, ㅡ=`U`, ㅏ=`IA`, ㅓ=`AI`, ㅗ=`AU`, ㅜ=`UA`, ㅢ=`UI`

### AA 경유 모음 (아래아 두 번 → 중간 경유지)
- `AA`는 ㆍ(아래아)로 표시되는 경유지이며, 완성 확정 시 ㆍ로 폴백
- ㅕ=`AAI`, ㅛ=`AAU`
- ㅑ=`IAA`, ㅖ=`AAII`, ㅒ=`IAAI`, ㅠ=`UAA`

### ㅗ 계열 복합모음
- ㅚ=`AUI`, ㅘ=`AUIA`, ㅙ=`AUIAI`

### ㅜ 계열 복합모음
- ㅟ=`UAI`, ㅝ=`UAAI`, ㅞ=`UAAII`
- `UAA(ㅠ)`는 동시에 ㅝ/ㅞ 경유지 역할 (AA 패턴과 동일)
- undo 역추적: ㅞ→ㅝ→ㅠ→ㅜ→ㅡ 순서로 한 stroke씩 복원

## 확정된 동작 결정사항
- 자음 토글(ㄴ→ㄹ 등) 임계값: **1초** (`DOUBLE_TOGGLE_THRESHOLD=1.0`)
- 무입력 자동 확정: **1초** (`AUTO_CONFIRM_TIMEOUT=1.0`)
- Backspace **1.5초 이상 꾹** 누르면 연속 삭제 시작, **0.08초** 간격으로 한 칸씩.
- Backspace 역추적: 확정 글자 삭제 시 HID backspace 전송됨 (`_emit_engine_output` 수정 완료).
- space: 조합 중이면 확정만, 빈 상태에서만 공백 추가.

## 진행 상황
### 묶음 1 (엔진 cheonjiin_engine_v2.py) — 완료 (코드+실기 검증)
1. **AA 경유지 추가**: `VOWEL_TABLE`에 `'AA':'ㆍ'` 추가. 이게 없으면 ㅕ/ㅛ/ㅑ/ㅒ/ㅖ/ㅠ 전부 실패함.
2. **복합모음 시퀀스 확정**: ㅚ=AUI, ㅘ=AUIA, ㅙ=AUIAI, ㅟ=UAI, ㅝ=UAAI, ㅞ=UAAII — 위 섹션 참고.
3. **모음+자음 씹힘 수정**: `HangulComposer.input_consonant`에 `not cho and jung` 분기 추가. 초성 없이 모음만 있는 상태에서 자음 누르면 모음 배출 후 새 초성 시작. 이 분기가 없으면 ㅏ/ㅣ/ㅕ 등 단독 모음 뒤에 자음이 씹힘.
4. **undo_stack 일관성**: 위 분기의 undo_stack 처리는 기존 `cho and not jung` 분기와 동일 패턴 — 배출된 모음은 committed로 올라가고 새 초성만 스택에 남음.
- ※ 최신본 확인: VOWEL_TABLE에 `'AA','UAI','UAAI','UAAII'` 키가 모두 있으면 최신본.

### 묶음 2 (main.py + engine) — 완료
1. **space 공백 버그 수정**: 조합중(`composer.is_empty()==False`) 상태에서 space → 확정만, 공백 없음. 빈 상태에서만 공백 추가. (`cheonjiin_engine_v2.py` space 핸들러 수정)
2. **영어 매핑 전체 교체**: `ENGLISH_CYCLE`을 스위치 번호가 아닌 엔진 토큰 기준으로 재작성. a-z 전체(토큰 '1'~'0') + 특수문자 `'4':['.', ',', '?', '!']`. 숫자가 나오던 버그 해결.
3. **Shift 쌍자음+영어 대문자**: GPIO15(스위치13) 중복 생성 방지 — `_init` 루프에서 `SHIFT_KEY_ID` skip 추가. `_handle_input_mode`의 shift 조건을 `if shift_held:` 로 확장. `_handle_english`에서 `_shift_pending` 체크해 `.upper()` 적용.
- ※ GPIO 하드웨어 검증 필요: 부팅 로그에서 "키패드 버튼 15개(13 없음) + Shift GPIO15 한 번만" 확인, 실제 Shift+자음/Shift+영문 버튼 테스트

### 묶음 3 (main.py) — 완료 (일부 실기 확인 중)
1. **backspace HID 수정**: `_emit_engine_output`에서 committed 줄어들 때 줄어든 수만큼 HID backspace 전송.
2. **자동확정 1초**: `_process_auto_confirm` 추가 — 조합 중 1초 무입력 시 자동 확정.
3. **backspace 연속삭제**: `_process_backspace_hold` 추가 — 1.5초 꾹 누르면 0.08초 간격 반복 삭제.
4. **자음 토글 임계값**: `DOUBLE_TOGGLE_THRESHOLD` 0.5 → 1.0.
5. **터미널 피드백**: 자동확정/연속삭제 시 `_show_input_state()` 추가.
- ※ 실기 확인 필요: 연속삭제 타이밍(1.5초/0.08초), 자동확정 1초 체감, 토글 1초 경계값.

### 묶음 5 (main.py — render-diff 실시간 조합) — 완료 (2026-06-10, 실기 통과)
- **구조 개요**: 천지인 조합(자모 시퀀스→완성 음절)은 라즈베리파이가 담당, 자모 단위 실시간 화면 표시는 윈도우 한글 IME가 담당. 전제: 노트북에 윈도우 한글 IME가 켜진 상태여야 함(현재 수동 전환).
1. **전송 구조 전환**: `_emit_engine_output`을 완성형 한글 직전 전송 → **두벌식 자모 render-diff** 방식으로 전면 교체. 기존엔 자동확정(1초) 후 완성형이 툭 나왔음. 변경 후 자모 입력 즉시 두벌식 키 전송 → 윈도우 IME가 ㄱ→기→가 과정을 밑줄로 실시간 표시.
2. **`_sent_keys` 추적 추가**: `__init__`에 `self._sent_keys: list = []` 추가. 조합 중인 음절의 "윈도우에 현재 보낸 키 목록"을 관리. `composer.render()` 결과를 `hangul_to_qwerty_keys()`로 변환, `_sent_keys`와 diff → 달라진 tail만 backspace+재입력. 모드 리셋·확정 시 초기화.
3. **아래아(ㆍ) 처리**: ㆍ는 두벌식에 없어 윈도우 미전송. ㆍ 경유 모음(ㅓ·ㅗ·ㅕ·ㅛ 등) 구간은 1~2타 멈췄다 합쳐짐 — 구조상 불가피, 허용 동작.
4. **실기 통과 항목 5개**: ① ㄱ 누르면 즉시 밑줄 ㄱ 표시 → ㅏ 누르면 '가'로 합쳐짐. ② 아래아 경유 모음(ㅕ·ㅛ 등) 구간 잠시 멈춤 후 정상 완성. ③ 자음 토글(ㄴ→ㄹ) 시 render-diff로 즉시 갱신. ④ 조합 중 backspace → 자모 단위 되돌림 + 윈도우 화면 동기화. ⑤ 도깨비불(받침→다음 초성 이동) 정상 동작.

### 묶음 6 (main.py — backspace 확정 글자 삭제) — 완료 (2026-06-10, 실기 통과)
1. **was_empty 패턴 추가**: `_handle_input_mode`의 'back' 처리에 `was_empty = composer.is_empty() and not engine.committed` 체크 추가. 내부 버퍼가 완전히 비어있을 때 backspace → HID backspace 1회 전송해 노트북 확정 글자 삭제.
2. **render-diff 연계**: 조합 중일 때는 render-diff가 `_sent_keys` 기반으로 처리. 조합 완전 종료(`is_empty` + `_sent_keys=[]`) 후 was_empty 체크로 전달.
3. **`_process_backspace_hold` 동일 패턴 적용**: 연속 삭제(꾹 누르기)도 동일 was_empty 로직 적용.
- ※ 실기 통과 항목 3개: ① 확정 후 backspace → 노트북 글자 삭제. ② 자음 단독 backspace → 윈도우 composing 취소. ③ 조합 중 → 확정 → 다시 backspace → 정상 연속 삭제.

### 묶음 7 (cheonjiin_engine_v2.py — backspace 팬텀 버그 근본 수정) — 완료 (2026-06-10, 실기 통과)
- **증상**: 모음(ㅣ/ㅡ/ㆍ)을 조합 중 여러 번 연속 입력 후 backspace 누르면 헛방 누적 후 나중에야 지워짐.
- **Origin 1 (주 원인)** — `HangulComposer.undo()` jung 분기, [cheonjiin_engine_v2.py:324](cheonjiin_engine_v2.py#L324):
  - VowelMachine 오버플로 시 vm.seq는 최신 stroke 1개만 남지만 undo_stack에는 모든 stroke 엔트리가 쌓임. seq 소진 후 남은 팬텀 엔트리를 undo할 때 vm.undo_stroke()가 False를 반환하지만 기존 코드가 이를 무시하고 항상 True 반환 → _backspace()가 committed를 건드리지 않고 리턴 → HID 미전송.
  - **수정**: `undone = self.vm.undo_stroke()` 후 `return undone`. 팬텀이면 False → _backspace()가 committed trim → _emit Section 1 → HID backspace 정상 전송.
  - vm.undo_stroke()는 seq가 이미 ''일 때만 False. 실제 stroke 소비 시('IA'→'I', 'I'→'')엔 True → 정상 조합 중 undo 동작 보존.
- **Origin 2 (보조)** — `HangulComposer.input_vowel_stroke()` else 분기, [cheonjiin_engine_v2.py:298](cheonjiin_engine_v2.py#L298):
  - 오버플로 시 초성 없는 상태에서 committed_vm='ㆍ'가 flushed에 추가돼 engine.committed에 쌓였음. ㆍ는 Windows에 미전송이므로 committed가 줄어들 때 HID backspace를 보내면 엉뚱한 글자 삭제.
  - **수정**: `if committed != 'ㆍ': flushed.append(committed)`. committed = "Windows에 실제 보낸 글자" 의미 유지.
  - 두 수정은 역할이 달라 둘 다 필요: Origin 2가 없으면 Origin 1 fix로 팬텀→committed trim 시 ㆍ 대응 HID backspace가 Windows 엉뚱한 글자 삭제.
- **실기 통과**: ㅣ×10·ㅡ×10·ㆍ×10 입력 후 backspace 헛방 없음 + 회귀 3개(확정 글자 삭제, 조합 중 자모 undo, ㄱ 단독 삭제).
- 커스텀 모드 backspace 연속삭제도 이 수정으로 함께 해결됨 — 실기 확인 완료 (2026-06-11).

### 묶음 4 (USB 가젯 부팅 설정) — 완료 (2026-06-10)
1. **config.txt 수정**: `[all]` 섹션에 `dtoverlay=dwc2,dr_mode=peripheral` 추가 → 라즈베리파이 USB를 device(gadget) 모드로 강제.
2. **cmdline.txt 수정**: `modules-load=dwc2,libcomposite` 추가 → 부팅 시 필요한 커널 모듈 자동로드.
   - ※ dwc2는 커널 built-in, libcomposite는 모듈; modules-load 파싱 이슈 있지만 부팅은 문제 없음.
3. **gadget_restore.sh HID 디스크립터 null 바이트 잘림 해결**: bash printf는 null 바이트(\x00)가 command substitution에서 잘렸음(59바이트). base64도 시도했으나 최종적으로 **python3 hex 방식**으로 변경 — 영구 해결:
   - Keyboard: `python3 -c "import sys; sys.stdout.buffer.write(bytes.fromhex('...'))" | sudo tee functions/hid.usb0/report_desc > /dev/null`
   - Mouse: 동일 방식 (report_length: 8 → 4 바이트)
   - ※ 검증: `od -A x -t x1z` 로 키보드 63바이트, 마우스 52바이트 확인.
4. **가젯 초기화 후 HID 동작 확인**: /dev/hidg0, hidg1이 character device로 생성됨. 노트북에서 한글 입력, 조이스틱 이동, 마우스 클릭 **모두 작동 확인**.

### 묶음 8 (main.py — 한/영 전환 + 영어 입력 수정) — 완료 (2026-06-11, 실기 통과)

#### 한/영 전환 동기화
1. **Right Alt(modifier 0x40)로 Windows IME 전환**: LANG1(0x90)은 이 노트북에서 미인식. Right Alt가 동작 확인. `HANGUL_HID_CANDIDATES` 상수에 후보 4개 정리(RALT/LANG1/LANG2/RCTRL), `HANGUL_HID = HANGUL_HID_CANDIDATES['RALT']` 한 줄만 바꾸면 다른 노트북에서도 적용 가능.
2. **공백 버그 수정**: 한/영 전환 시 `_flush_engine()` 대신 직접 처리. 조합 중일 때만 `engine.press("space")`(확정만, 공백 없음), 빈 상태면 아무것도 안 함.
3. **시작 동기화 (방법 C)**: USB HID 단방향이라 완벽 자동 동기화 불가. 시작 시 터미널에 `[MODE: KO]` 표시 + "윈도우 IME 상태 확인" 안내 출력. 어긋났으면 노트북 물리 키보드로 Windows 쪽만 맞추고 시작. 이후 Pi 한/영키로 양쪽 동시 토글 → 동기화 유지.
   - ※ 맞추는 방법: 라즈베리파이 한/영키는 양쪽 동시 토글이라 어긋남 해소 불가. 어긋났으면 노트북 키보드로 Windows만 맞춰야 함.

#### 영어 입력 수정
4. **영어 사이클 깨짐 수정**: render-diff 도입(묶음 5) 후 영어 사이클(a→b→c)이 막혔음. 원인: 사이클 치환은 committed 길이 불변 → Section 1/2 모두 스킵. `_emit_engine_output`에 **Section 1.5** 추가 — `curr_len==prev_len && full!=_last_committed` 조건 → 공통 접두사 이후 backspace+새글자 전송.
5. **특수문자 Shift 조합 수정**: `send_char_key`가 `?`·`!` 등 Shift 조합 문자를 `HID_KEYCODES`에 없다고 SKIP하던 버그. `elif ch in SYMBOL_TO_KEY:` 분기 추가 — `?`=Shift+`/`, `!=`Shift+`1`. Section 1.5·Section 2 양쪽에서 동작.
   - ※ 실기 통과: `. , ? !` 순환 정상, backspace 후 정상 삭제.

### 묶음 9 (부팅 자동화) — 완료 (2026-06-11, 실기 통과)
1. **systemd 서비스 `cheonjiin.service` 생성·enable**: `ExecStartPre=gadget_restore.sh` → `ExecStart=main.py` 순서로 부팅 시 자동 실행. `/etc/systemd/system/cheonjiin.service`.
2. **안전 설계**: `Requires=` 없음, `After=local-fs.target`만, `WantedBy=multi-user.target`. 서비스 실패해도 부팅/SSH 안 막힘 — 실제 재부팅으로 검증됨.
3. **gadget_restore.sh stub 처리 추가** (3단계 대책):
   - ① 0단계: UDC 바인드 전 `/dev/hidg*` 일반 파일 stub 사전 삭제
   - ② 3단계: configfs 가젯 제거를 올바른 순서로 — 링크→config→function→strings→루트. `rm -rf`는 configfs 가상 파일시스템에 안 먹힘, `rmdir` 순서 필수.
   - ③ 5.5단계: UDC 바인드 후 `mknod` fallback — udev가 느리거나 실패 시 `/sys/class/hidg/hidg*/dev`에서 major:minor 읽어 수동 생성.
4. **재부팅 테스트 통과**: SSH 정상 재접속, 서비스 `active(running)` 자동 시작, 노트북 키 입력·조이스틱 작동 확인.
5. **비상 복구**: `sudo systemctl stop cheonjiin` → `disable` → `mask` 순서로 SSH에서 제어 가능.

### 묶음 10 (web_setter + 펌웨어 소수 버그 수정) — 완료 (2026-06-14, 실기 통과)
1. **web_setter `+` 키 저장 버그 수정** (`web_setter.py`): `parse_qs(raw)`가 `+`를 공백으로 디코딩하던 문제. `do_POST`에서 `raw.replace('+', '%2B')` 전처리 추가. 기존 `ctrl+c`(브라우저가 `ctrl%2Bc`로 전송) 영향 없음. config.json에 `"+"` 정상 저장 실기 확인.
2. **14번 키 토글 순서 수정** (`cheonjiin_engine_v2.py`): `CONSONANT_TOGGLE '4': ['ㅁ','ㅇ']` → `['ㅇ','ㅁ']`. 천지인 표준(첫 입력=ㅇ, 토글=ㅁ). 배열 인덱스만 바꾸므로 다른 자음 토글·조합 로직에 영향 없음. 실기 통과.
3. **13번 키 커스텀 모드 입력 버그 수정** (`main.py`): `SHIFT_KEY_ID(13)`은 `self.buttons`에서 제외돼 커스텀 모드 콜백이 없었음. `_bind_gpio_callbacks`에 `shift_button.when_pressed` 추가 — **커스텀 모드에서만** `on_key_press(13)` 호출, 한글 입력 모드에서는 아무것도 안 함(`is_pressed` 폴링 보존). 실기 통과 — 커스텀 13번 입력 정상, 한글 모드 shift 쌍자음 회귀 없음.
4. **커스텀 모드 매크로 실기 검증**: Ctrl+z/c/v 노트북에서 정상 동작 확인. 기존 "미검증" 항목 해결 — 코드 경로 정상이었음.

### 묶음 11 (web_setter 드래그앤드롭 재설계) — 완료 (2026-06-14, 실기 통과)
- **서버 로직(load_config/save_config/normalize_key)은 일절 안 건드리고 `render_page()`만 전면 교체.**
1. **화이트 베이스 + 블랙 포인트 디자인**: body `#f4f4f4`, 셀 `#fff`, 배지 `#111` 블랙 악센트.
2. **16키 그리드**: 단일 문자 → 텍스트 입력(`maxlength=1`, datalist 제거). 조합 매크로 → 하단 카드 드래그해서 키에 드롭 → 배지("복사 / ctrl+c" 두 줄) + hidden input으로 값 보관. X 버튼으로 해제하면 텍스트 입력 복귀.
3. **드롭 가능 범위**: 1~15번 전부 가능(숫자키 포함), 16번 고정키만 제외. 드래그 오버 시 `drop-over` 테두리 하이라이트.
4. **상태 유지**: hidden input으로 POST 전송 → config.json 저장 → 새로고침 시 Python이 preset_val_to_lbl 역참조로 배지 재생성. 기존 저장값이 프리셋이면 로드 즉시 배지+X 버튼 표시.
5. **카드 목록(PRESET_ITEMS)**: 클립보드(ctrl+c/v/x), 실행취소(ctrl+z/y), 편집(ctrl+a/s/f), 앱제어(alt+f4), 방향키 4개, 기본키(enter/backspace/tab/esc/space) — 총 18개.
6. **datalist 완전 제거**: 텍스트칸은 단일 문자 전용(maxlength=1)이므로 기능키 자동완성 불필요.

### 묶음 12 (web_setter 조이스틱 슬라이더 + 레이아웃) — 완료 (2026-06-16, 실기 통과)
1. **펌웨어(main.py) — config.json 연동**: `MOUSE_SPEED`, `RIGHT_CLICK_HOLD` 상수를 인스턴스 변수(`self.mouse_speed`, `self.right_click_hold`)로 전환. `_process_config_reload()`에서 1초마다 읽어 갱신(try/except fallback). 조이스틱 동작 자체는 안 건드림. `_axis_to_delta`에서 `@staticmethod` 제거 → `self.mouse_speed` 참조, `_process_joystick_button`에서 `self.right_click_hold` 참조.
2. **web_setter.py — 저장 분리(머지 보존)**: `load_joystick_config()` / `save_joystick_config()` 추가. `save_config()`가 항상 조이스틱 값을 머지해서 보존 — 키 매핑 저장/기본값 복원 시 조이스틱 값 안 날아감. `/save` POST에서 슬라이더 값 같이 읽어 저장, `/reset`에서 `JOYSTICK_DEFAULTS`로 초기화.
3. **web_setter.py — 슬라이더 UI**: 조이스틱 패널(왼쪽 컬럼)에 속도(1~30)·우클릭 감지(0.1~2.0s) range 슬라이더. `form="mainform"` 속성으로 오른쪽 키 그리드 form에 연결 — 저장하기 버튼 하나로 키보드+조이스틱 동시 저장. 기본값 복원도 동일.
4. **디자인**: 검정 뉴모피즘 다이얼(CSS 동심원, 장식용). 왼쪽 컬럼(조이스틱 패널+버튼) / 오른쪽 컬럼(키 그리드+매크로 카드) 2열 레이아웃. 조이스틱 패널 높이는 JS(`alignJoyPanel`)로 실제 셀 높이 측정 후 동적 설정(3행+2갭) — 브라우저/줌 무관하게 9번 키 하단과 정렬.
   - 레이아웃 수치: `layout max-width: 1000px`, `left-col-wrap: 280px`, right-col `flex:1` → 그리드 696px 고정. layout max-width와 left-col-wrap를 같은 폭(+40px)으로 조정해야 그리드 크기 안 바뀜.
   - ※ 실기 통과: 슬라이더 값 조이스틱 반영, 키 저장/기본값 복원 시 조이스틱 값 보존.

### 포기한 작업 (기록용)
- **USB RNDIS 고정 주소**: Windows 10 1903+ 에서 RNDIS 드라이버 자동 설치가 제거됨. bDeviceClass=0xEF 복합 모드 시도 시 RNDIS 드라이버 미설치로 HID까지 같이 죽는 현상 발생. 위험 대비 이득 없어 포기. **web_setter는 핫스팟+IP(192.168.45.x:8000)로 접속.**
- **윈도우 mDNS(9jo.local)**: 우선순위 낮아 진행 안 함.

### 묶음 13 (핫스팟 고정 IP) — 완료 (2026-06-17, 실기 통과)
1. **고정 IP 172.20.10.14 설정**: 아이폰 핫스팟 "노인"(172.20.10.0/28 대역)에서 라즈베리파이가 항상 같은 IP를 받도록 NetworkManager 프로파일 수정. `nmcli connection modify "노인" ipv4.method manual ipv4.addresses "172.20.10.14/28" ipv4.gateway "172.20.10.1" ipv4.dns "8.8.8.8"`. 백업: `노인.nmconnection.bak`.
2. **집 와이파이 무영향**: SK_E7A4_5G 등 다른 SSID는 별도 프로파일 → 기존 DHCP 그대로 유지.
3. **발표 접속법**: 핫스팟 "노인" 켜기 → 노트북도 같은 핫스팟 연결 → `172.20.10.14:8000` (모니터·IP 확인 불필요).
4. **주의**: 노트북이 집/학교 와이파이로 자동 전환되면 라즈베리파이와 다른 네트워크가 돼 접속 불가. 발표 시 노트북이 핫스팟에 붙어있는지 확인 필수.
5. **복구**: `sudo nmcli connection modify "노인" ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""` → `sudo nmcli connection up "노인"`. 또는 `.bak` 복원 후 `sudo nmcli connection reload`.
   - DHCP 충돌 참고: 172.20.10.14는 /28 범위 맨 끝 — 아이폰 DHCP가 .2부터 올라오므로 발표 환경(2~3기기)에서 충돌 가능성 최소.

## 발표 당일 체크리스트

### 준비 (발표 전)
1. **아이폰 핫스팟 "노인" 켜기**
2. **라즈베리파이 전원 → USB C타입으로 노트북에 연결** (HID + 전원 동시)
3. **노트북을 핫스팟 "노인"에 연결** (다른 와이파이 자동 전환 주의 — 연결 상태 확인)
4. **서비스 자동 시작 대기** (부팅 후 약 10~15초) — cheonjiin.service가 gadget_restore.sh 실행 후 main.py 기동
5. **노트북 키보드로 윈도우 한글 IME 켜기** (라즈베리파이 시작 시 `[MODE: KO]` 상태 → 윈도우도 한글 모드여야 동기화)

### 동작 확인
6. **HID 입력 테스트**: 라즈베리파이 키 눌러서 한글 입력되는지 확인
7. **web_setter 접속**: 브라우저에서 `http://172.20.10.14:8000` — 키 설정 페이지 뜨는지 확인
8. **조이스틱 동작**: 마우스 커서 이동·클릭 확인

### 발표 중 주의
- 노트북 와이파이가 자동으로 다른 네트워크로 바뀌면 web_setter 접속 끊김 → 핫스팟 재연결
- 한/영 모드 어긋나면: 라즈베리파이 12번 키(한/영)로 양쪽 동시 토글. 그래도 안 맞으면 노트북 키보드로 윈도우 IME만 전환
- HID 끊기면(USB 빠짐): C타입 재연결 → 서비스 자동 재시작

## 프로젝트 완료 상태 (2026-06-17)
전체 기능 구현 + 실기 통과 + 발표 환경 설정 완료. 추가 작업 없음.