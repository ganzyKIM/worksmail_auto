# 네이버 웍스 공용 메일함 요약

네이버 웍스 공용 계정(info, base 등)에 들어온 메일을 모아 Gemini로 요약하고, 정해진 시각에 담당자들에게 메일로 보내는 프로그램이다.
보이스 웹툰 제작사 두비덥에서 쓰려고 만든 사내 도구다.
Windows PC 한 대에서 작업 스케줄러로 돌린다. 설정은 로컬 관리자 화면에서 바꾼다.

```
작업 스케줄러가 10분마다 run_watch_once.bat 실행
  → 발송 시각이 지났는지 확인 (아니면 그냥 종료)
  → IMAP으로 계정별 새 메일 수집 (메일함을 읽기 전용으로 열어 읽음 표시는 그대로)
  → Gemini API로 요약 리포트 작성
  → SMTP로 수신자들에게 발송
```

## 요약 메일 형식

- 맨 위 "오늘 꼭 챙길 것": 계약, 결제, 마감, 클레임 같은 급한 건 최대 5개
- 계정마다 섹션 하나. 메일 한 통이 표 한 줄이다 (중요도, 분류, 보낸사람, 한줄요약, 필요한 조치)
- 새 메일이 0건인 계정도 섹션을 만든다
- Gemini 호출이 실패하면 요약 없이 수집한 메일 목록만 보낸다

본문은 Markdown으로 받아 HTML 메일로 바꾼다. 프롬프트는 `worksmail_digest.py`의 `build_prompt()`에 있다.

## 설치

Windows와 Python 3.11 이상이 필요하다. 테스트는 Python 3.12에서 돌렸다.

### 설치 파일로

```powershell
powershell -File installer\build_installer.ps1
```

`dist\WorksMailSetup.exe`가 만들어진다. Windows 내장 IExpress로 묶기 때문에 따로 깔 도구가 없다.
설치 파일을 새 PC에서 실행하면 아래 순서로 진행된다.

1. 설치 폴더 선택 (기본값은 바탕화면 아래 `worksmail`)
2. `.venv` 가상환경 생성, 패키지 설치
3. `config.example.yaml`을 `config.yaml`로 복사 (이미 있으면 그대로 둠)
4. 작업 스케줄러에 `WorksMail Watch` 등록 (10분 간격)
5. 관리자 화면과 `SETUP_GUIDE.html` 열기

Python이 없으면 python.org 다운로드 페이지를 열지 묻고 설치를 멈춘다.

### 손으로

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

작업 스케줄러 등록은 관리자 권한 PowerShell에서 한다. 경로는 설치 폴더에 맞게 바꾼다.

```powershell
$taskPath = "C:\path\to\worksmail\run_watch_once.bat"
schtasks /Create /SC MINUTE /MO 10 /TN "WorksMail Watch" /TR $taskPath /RL LIMITED /F
```

`/TR`에 따옴표를 이스케이프해서 바로 넣으면 PowerShell이 인자를 깨뜨린다. 변수에 담아 넘긴다.

## 네이버 웍스 쪽 준비

- 관리자 콘솔의 서비스 > Mail > IMAP/POP3에서 IMAP 사용 허용
- 2단계 인증을 켠 계정은 개인 설정 > 보안 > 앱 비밀번호에서 발급한 비밀번호를 사용
- Gemini API 키는 [Google AI Studio](https://aistudio.google.com/apikey)에서 발급

## 설정

환경 변수는 쓰지 않는다. 모든 값은 `config.yaml` 하나에 들어간다. 틀은 `config.example.yaml`이다.

| 키 | 내용 | 기본값 |
| --- | --- | --- |
| `imap.host`, `imap.port` | IMAP 서버 | `imap.worksmobile.com`, 993 |
| `smtp.host`, `smtp.port` | SMTP 서버 (STARTTLS) | `smtp.worksmobile.com`, 587 |
| `accounts` | 수집할 공용 계정 목록 (`name`, `email`, `password`) | 없음 |
| `sender` | 요약을 보낼 계정 (`email`, `password`, `display_name`) | 없음 |
| `recipients` | 요약을 받을 주소 목록 | 없음 |
| `gemini.api_key` | Gemini API 키 | 없음 |
| `gemini.model` | 모델 이름 | `gemini-flash-latest` |
| `lookback_hours` | 첫 수동 실행 때 거슬러 볼 시간 | 24 |
| `body_char_limit` | 메일 한 통에서 프롬프트에 넣을 최대 글자 수 | 2000 |
| `schedule.interval_hours` | 발송 간격(시간) | 24 |
| `schedule.anchor_time` | 첫 발송 시각 (`HH:MM`) | `08:00` |
| `admin_ui.password` | 관리자 화면 비밀번호 | 비어 있음 (첫 접속 때 정함) |

모델은 `-latest` 별칭을 기본으로 둔다. `gemini-2.5-flash`처럼 버전을 고정하면 구글이 모델을 내릴 때 404가 난다.

`config.yaml`에는 메일 비밀번호와 API 키가 평문으로 들어간다. `.gitignore`에 들어 있다. `state.json`과 `worksmail.log`도 마찬가지다.

## 관리자 화면

```powershell
python admin_ui.py
```

`run_admin_ui.bat`을 더블클릭해도 된다. `http://127.0.0.1:5000`에서 열리고 다른 기기에서는 접속할 수 없다.

- 첫 접속 때 관리자 비밀번호 설정 (4자 이상)
- 수집 계정 추가, 삭제, 비밀번호 변경
- 수신자 추가, 삭제
- 발송 계정 선택
- 발송 간격과 첫 발송 시각 변경
- Gemini 키와 모델 변경
- 연결 테스트 (IMAP, SMTP, Gemini에 접속해 결과 표시)
- `worksmail.log` 마지막 25줄

저장하면 `config.yaml` 전체를 다시 쓴다. 손으로 단 주석은 사라진다. 세션 키는 서버를 켤 때마다 새로 만들어서 재시작하면 다시 로그인해야 한다.

## 명령줄

| 명령 | 동작 |
| --- | --- |
| `python worksmail_digest.py --test` | IMAP, SMTP, Gemini 연결만 확인 |
| `python worksmail_digest.py --dry-run --since-hours 48` | 최근 48시간 메일을 요약해 화면에만 출력 |
| `python worksmail_digest.py` | 마지막 실행 이후 메일을 요약해 바로 발송 |
| `python worksmail_digest.py --date 2026-07-15` | 그날 하루치 메일만 요약해 발송 (`state.json`은 그대로) |
| `python worksmail_digest.py --watch-once` | 발송 시각이 지났을 때만 수집하고 발송. 작업 스케줄러용 |

발송하는 명령에 `--dry-run`을 붙이면 보내지 않고 화면에만 출력한다. `--since-hours`, `--date`, `--watch-once`는 하나만 고른다.
`run.bat`은 스케줄을 무시하고 바로 한 번 보낸다.

## 스케줄 동작

- `--watch-once`를 처음 실행하면 `anchor_time` 기준으로 첫 발송 시각만 정하고 끝낸다
- 그 뒤로는 점검할 때마다 `state.json`의 `next_due`와 현재 시각을 비교한다
- 발송 시각이 지났으면 직전 간격만큼의 메일을 모아 보낸다
- 다음 발송 시각은 보낸 시각이 아니라 예정 시각에 간격을 더해 정한다. 점검이 10분 단위라 보낸 시각을 기준으로 하면 회차마다 몇 분씩 밀린다
- 발송에 실패하면 `next_due`를 그대로 두고 다음 점검 때 다시 시도한다
- 관리자 화면에서 스케줄을 저장하면 `next_due`를 지우고 첫 발송 시각부터 다시 계산한다

같은 저장소를 PC 두 대에서 동시에 돌리면 요약이 두 번 나간다. PC를 옮길 때는 예전 PC의 작업부터 지운다.

```powershell
schtasks /Delete /TN "WorksMail Watch" /F
```

`config.yaml`은 저장소에 없으니 USB 같은 오프라인 수단으로 따로 옮긴다. `state.json`도 같이 옮기면 스케줄이 이어진다.

## 테스트

```powershell
pip install -r requirements-dev.txt
pytest -v
```

메일 서버 없이 도는 단위 테스트 74개다. MIME 디코딩, 본문 추출, 날짜 구간 계산, 설정 검증, Gemini 응답 파싱, `--watch-once` 스케줄 갱신을 확인한다.

## 구조

```
worksmail_digest.py        수집, 요약, 발송, 스케줄 판단 (CLI)
admin_ui.py                Flask 관리자 화면. worksmail_digest의 함수를 가져다 씀
templates/                 관리자 화면 HTML
static/fonts/              관리자 화면 서체 (Galmuri11, OFL)
installer/                 설치 파일 빌드 스크립트와 설치 스크립트 (PowerShell)
SETUP_GUIDE.html           설치 직후 여는 안내 페이지
run*.bat                   가상환경을 켜고 각 모드를 실행하는 배치 파일
test_worksmail_digest.py   pytest 테스트
config.example.yaml        설정 틀
```

## 기술 선택

- Gemini는 SDK 없이 `requests`로 REST API를 부른다. 의존성은 `requests`, `PyYAML`, `markdown`, `Flask` 네 개다.
- IMAP 검색은 날짜 단위라서 하루 넓게 받아 온 뒤 `Date` 헤더로 시각을 다시 거른다.
- 설치 파일은 프로젝트를 zip 하나로 묶어 IExpress에 넣는다. IExpress가 하위 폴더 구조를 평평하게 풀어 버려서 고른 방법이다.
- Windows 콘솔의 cp949 인코딩에서 출력이 죽지 않도록 표준 출력을 UTF-8로 바꾼다.
