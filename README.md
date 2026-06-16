# 천지인 16키 USB HID 키보드

라즈베리파이를 USB HID 키보드·마우스로 동작시켜, 16키 천지인 배열로 한글을 입력하는 펌웨어.

라즈베리파이 내부에서 천지인 자모를 조합하고, **두벌식 자모 키(QWERTY)로 변환해 노트북에 전송** → 윈도우 기본 한글 IME가 실시간 조합한다.  
브라우저 기반 설정 페이지(`web_setter`)로 커스텀 키 매핑·조이스틱 감도를 실시간 변경할 수 있다.

---

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `main.py` | 메인 펌웨어 — HID 전송, 스위치 입력, 모드 전환, 조이스틱, 자동확정 등 |
| `cheonjiin_engine_v2.py` | 천지인 조합 오토마타 엔진 (자모 시퀀스 → 완성 한글) |
| `web_setter.py` | 브라우저 기반 설정 서버 (포트 8000) — 키 매핑, 조이스틱 감도 설정 |
| `config.json` | 키 매핑·조이스틱 설정 저장 파일 (펌웨어가 1초마다 자동 반영) |
| `gadget_restore.sh` | USB 가젯 초기화 스크립트 (HID 키보드·마우스 디스크립터 등록) |
| `gadget_remove.sh` | USB 가젯 제거 스크립트 |

### 테스트 파일 (개발·디버그용)

| 파일 | 역할 |
|------|------|
| `test_button.py` | GPIO 버튼 입력 테스트 |
| `test_joystick.py` | 조이스틱 ADC 값 확인 |
| `test_keyboard.py` | HID 키보드 전송 테스트 |
| `test_switch.py` | 스위치 배선 확인 |
| `test_scan_all.py` | 전체 GPIO 스캔 |
| `test_mcp_full.py` | MCP3008 ADC 통신 테스트 |

---

## 하드웨어 요구사항

- **Raspberry Pi Zero 2W** (USB OTG dwc2 지원 필요)
- 16키 키패드 (GPIO 연결)
- 조이스틱 모듈 + **MCP3008** ADC (SPI)
- USB C타입 케이블 (노트북 연결 — 전원 + HID 동시)

---

## 설치 및 초기 설정

### 1. 저장소 클론

```bash
git clone https://github.com/nnoinn/rasp_cheonjiin_keyboard.git
cd rasp_cheonjiin_keyboard
```

### 2. USB 가젯 모드 활성화

`/boot/firmware/config.txt` 맨 아래 `[all]` 섹션에 추가:

```
dtoverlay=dwc2,dr_mode=peripheral
```

`/boot/firmware/cmdline.txt` 에서 `rootwait` 뒤에 추가 (한 줄, 줄바꿈 없이):

```
modules-load=dwc2,libcomposite
```

재부팅:

```bash
sudo reboot
```

### 3. USB 가젯 초기화 스크립트 실행 권한

```bash
chmod +x gadget_restore.sh gadget_remove.sh
sudo bash gadget_restore.sh
```

정상이면 `/dev/hidg0`(키보드), `/dev/hidg1`(마우스) 생성 확인:

```bash
ls -l /dev/hidg*
# crw------- 1 root root 236, 0 ...  /dev/hidg0
# crw------- 1 root root 236, 1 ...  /dev/hidg1
```

### 4. Python 의존성 설치

```bash
pip3 install gpiozero RPi.GPIO spidev
```

### 5. systemd 서비스 등록 (부팅 자동 시작)

`/etc/systemd/system/cheonjiin.service` 생성:

```ini
[Unit]
Description=Cheonjiin 16-key USB HID Keyboard
After=local-fs.target

[Service]
ExecStartPre=/home/pi/rasp_cheonjiin_keyboard/gadget_restore.sh
ExecStart=/usr/bin/python3 /home/pi/rasp_cheonjiin_keyboard/main.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

> 경로는 실제 클론 위치에 맞게 수정.

서비스 등록·시작:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cheonjiin
sudo systemctl start cheonjiin
sudo systemctl status cheonjiin
```

---

## 사용법

### 입력 모드 전환

- **16번 키**: 한글 입력 ↔ 커스텀(매크로) 모드 전환
- **12번 키**: 한/영 전환 (Windows IME 동기화)

### 천지인 모음 입력 (I=ㅣ, A=ㆍ, U=ㅡ)

| 모음 | 시퀀스 | 모음 | 시퀀스 |
|------|--------|------|--------|
| ㅏ | I→A | ㅓ | A→I |
| ㅗ | A→U | ㅜ | U→A |
| ㅕ | A→A→I | ㅛ | A→A→U |
| ㅑ | I→A→A | ㅠ | U→A→A |
| ㅘ | A→U→I→A | ㅝ | U→A→A→I |

### Backspace 동작

- **짧게**: 자모 단위 되돌림 (조합 중) / 확정 글자 삭제
- **1.5초 꾹**: 연속 삭제 시작 (0.08초 간격)

### 자동 확정

조합 중 1초 무입력 시 자동 확정.

---

## web_setter — 브라우저 설정 페이지

서비스 실행 중 자동으로 포트 8000에서 웹 서버가 뜸.

**접속**: `http://<라즈베리파이_IP>:8000`

- 16키 매핑을 텍스트 입력 또는 매크로 카드 드래그로 변경
- 조이스틱 속도(1~30), 우클릭 감지 시간(0.1~2.0s) 슬라이더 조정
- **저장하기**: 키 매핑 + 조이스틱 설정 동시 저장 (1초 안에 펌웨어 자동 반영)
- **기본값 복원**: 기본 숫자패드 배열 + 조이스틱 기본값으로 초기화

### 핫스팟 환경 고정 IP 접속

아이폰 핫스팟 사용 시 라즈베리파이 고정 IP 설정 방법:

```bash
sudo nmcli connection modify "핫스팟이름" \
    ipv4.method manual \
    ipv4.addresses "172.20.10.14/28" \
    ipv4.gateway "172.20.10.1" \
    ipv4.dns "8.8.8.8"
sudo nmcli connection up "핫스팟이름"
```

이후 항상 `http://172.20.10.14:8000` 으로 접속 가능.

---

## 비상 복구

서비스 문제 시 SSH에서:

```bash
sudo systemctl stop cheonjiin    # 중지
sudo systemctl disable cheonjiin # 자동시작 해제
sudo systemctl mask cheonjiin    # 완전 차단
```
