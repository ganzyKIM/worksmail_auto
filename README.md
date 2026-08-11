# 네이버 웍스 공용계정 메일 요약

info·base 같은 **공용 업무 계정**의 받은 메일을 정해진 간격으로 자동으로 모아, 제미나이(Gemini)로
요약·중요도 분류한 뒤 지정한 사람들에게 보내주는 프로그램입니다.

```
설정한 취합 간격마다 (기본: 매일 08:00 한 번)
  → IMAP으로 각 공용계정의 '새 메일' 수집 (읽음 표시는 안 건드림)
  → Gemini API로 계정별 요약 + 중요도/분류/필요조치 정리
  → SMTP로 등록된 수신자들에게 요약 메일 발송
```

모니터링 계정·수신자·취합 간격·발송 시각은 **브라우저 관리자 UI**(`admin_ui.py`)로
편집합니다. `config.yaml`을 직접 손으로 고쳐도 되지만, UI 쪽이 실수가 적습니다.

---

## 🚀 새 PC라면: 원클릭 설치 (제일 쉬운 방법)

`dist\WorksMailSetup.exe` 파일 하나만 새 PC로 옮겨서 더블클릭하면 됩니다.
압축 풀기·명령어 입력 전혀 필요 없습니다.

1. `WorksMailSetup.exe`를 USB 등으로 새 PC에 복사
2. 더블클릭 실행
3. 설치할 폴더 선택 (기본: 바탕화면 안에 `worksmail` 폴더)
4. 자동으로 진행되는 것 (몇 분 걸림):
   - 파일 설치
   - 파이썬 가상환경 + 필요한 패키지 설치
   - 작업 스케줄러에 자동 실행 등록 (10분마다 확인)
5. 끝나면 **관리자 화면(브라우저)과 안내 페이지가 자동으로 열립니다.**
   안내 페이지 순서대로 계정·수신자·Gemini 키만 입력하면 완료.

> Python이 설치되어 있지 않으면 안내 메시지가 뜨고, Python 설치 페이지를 열어줍니다.
> Python 설치 후 설치 프로그램을 다시 실행하면 됩니다.

**설치 파일을 다시 만들어야 할 때** (코드를 수정한 뒤 등):
```powershell
powershell -File installer\build_installer.ps1
```
`dist\WorksMailSetup.exe`가 새로 만들어집니다. (내부적으로 Windows 내장 도구인
IExpress를 사용 — 별도 설치 프로그램 필요 없음)

아래 1~9번은 원클릭 설치가 자동으로 해주는 과정을 하나씩 손으로 하는 방법입니다.
문제가 생겼을 때 참고하거나, 설치 없이 직접 이해하고 싶을 때 보세요.

---

## 0. 준비물 체크리스트

- [ ] 각 공용계정(info, base 등)의 **로그인 정보** 또는 **앱 비밀번호**
- [ ] 네이버 웍스 관리자 콘솔에서 **IMAP 사용 허용**이 켜져 있을 것
- [ ] **제미나이 API 키** (회사 계정으로 발급)
- [ ] 이 PC에 **Python 설치** (이미 3.11 확인됨)

---

## 1. 네이버 웍스 쪽 설정

### 1-1. IMAP 사용 허용 (관리자)
관리자 콘솔 → **서비스 > Mail > IMAP/POP3** 에서 IMAP 사용을 **허용**으로 둡니다.
(조직 전체 또는 해당 계정에 대해 허용되어 있어야 프로그램이 메일을 읽을 수 있습니다.)

### 1-2. 앱 비밀번호 발급 (2단계 인증을 쓰는 계정)
2단계 인증이 켜진 계정은 일반 비밀번호로 IMAP 로그인이 안 됩니다.
각 계정으로 로그인 → **개인 설정 > 보안 > 앱 비밀번호**에서 비밀번호를 발급받아
`config.yaml` 의 `password` 에 넣으세요. (2단계 인증을 안 쓰면 그냥 로그인 비밀번호 사용)

> 서버 주소는 기본값 그대로면 됩니다: IMAP `imap.worksmobile.com:993`,
> SMTP `smtp.worksmobile.com:587`

---

## 2. 제미나이 API 키 발급

1. https://aistudio.google.com/apikey (회사 구글 계정으로 로그인)
2. **Create API key** 클릭 → 생성된 키 복사
3. `config.yaml` 의 `gemini.api_key` 에 붙여넣기

기본 모델은 `gemini-flash-latest`(빠르고 저렴, 항상 최신 안정판을 자동으로 가리킴)입니다.
더 정교한 요약을 원하면 `gemini-pro-latest` 로 바꾸세요. (`gemini-2.5-flash`처럼 버전을
못박은 이름은 구글이 구버전을 내리면 어느 날 갑자기 404가 날 수 있어 권장하지 않습니다.)

---

## 3. 설치 (최초 1회)

PowerShell을 열고 이 폴더에서 실행:

```powershell
cd C:\Users\kimdh\Desktop\worksmail
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> `Activate.ps1` 실행이 막히면 한 번만:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 후 다시 시도하세요.

---

## 4. 설정 파일 작성

가장 먼저 `config.yaml`이 존재해야 관리자 UI든 CLI든 동작합니다. 최초 1회만 아래처럼
빈 틀을 만들어두고, 나머지(계정/수신자/스케줄/API 키)는 **관리자 UI에서 채우는 것을
권장**합니다 (5번 섹션 참고). UI 없이 직접 편집하고 싶다면 이 방법도 가능합니다:

```powershell
Copy-Item config.example.yaml config.yaml
notepad config.yaml
```

- `accounts`: 수집할 공용계정들 (이름/이메일/비밀번호). 필요한 만큼 추가
- `sender`: 요약 메일을 **보낼 때** 쓸 계정 (공용계정 중 하나여도 됨)
- `recipients`: 요약을 **받을** 사람들 목록 — 줄만 추가/삭제하면 됩니다
- `gemini.api_key`: 제미나이 키
- `schedule.interval_hours` / `schedule.anchor_time`: 취합 간격과 발송(기준) 시각

> ⚠️ `config.yaml` 에는 비밀번호가 들어갑니다. 외부에 공유하거나 클라우드에 올리지 마세요.

저장 후 다음 실행부터 바로 반영됩니다(재시작/재설치 불필요).

---

## 4-1. 관리자 UI로 설정 관리하기

계정·수신자·취합 간격·발송 시각을 매번 YAML 문법 신경 쓰며 손으로 고치는 대신,
브라우저에서 편집할 수 있는 관리자 화면입니다.

### 실행
```powershell
.\.venv\Scripts\Activate.ps1
python admin_ui.py
```
(또는 `run_admin_ui.bat` 더블클릭). 콘솔에 뜨는 주소로 브라우저에서 접속:
**http://127.0.0.1:5000**

- 이 서버는 **이 PC(127.0.0.1)에서만** 접속 가능합니다. 네트워크의 다른 PC나
  휴대폰에서는 열리지 않습니다.
- 콘솔 창을 닫으면 서버도 함께 종료됩니다. 평소엔 꺼둬도 되고, 설정을 바꿀 때만 켜세요.

### 최초 접속
비밀번호가 아직 없으면 "초기 설정" 화면이 뜹니다. 원하는 비밀번호를 정하세요
(이후 로그인에 사용, `config.yaml`의 `admin_ui.password`에 저장됩니다).

### 화면 구성
- **모니터링할 메일주소 목록**: info/base 같은 공용 계정 추가·삭제, 계정별 비밀번호 변경
- **요약 메일을 받을 수신자**: 받는 사람 추가·삭제
- **발송 계정**: 요약 메일을 실제로 보낼 때 쓸 계정 선택 (모니터링 계정 중 하나)
- **취합 단위 & 발송 시각**: 몇 시간 간격으로, 몇 시를 기준으로 발송할지
  (예: 12시간 간격 + 08:00 기준 → 매일 08:00·20:00 두 번 발송)
- **Gemini API**: 키/모델 (비워두고 저장하면 기존 값 유지)
- **연결 테스트**: 저장된 설정으로 IMAP/SMTP/Gemini에 실제 접속해보고 결과 표시
- **최근 로그**: `worksmail.log` 마지막 부분을 바로 확인

저장 버튼을 누르면 `config.yaml` 전체를 다시 씁니다 — **손으로 넣은 주석은 저장 후
사라집니다.** (값 자체는 안전하게 보존됩니다.)

---

## 4-2. (개발자용) 자동 테스트

핵심 로직(제목 디코딩, 본문 추출, 날짜 처리, 프롬프트 생성, 설정 검증 등)은
실제 메일 서버 없이도 pytest로 검증됩니다. 코드를 수정했다면 실행해보세요:

```powershell
pip install -r requirements-dev.txt
pytest -v
```

---

## 5. 동작 테스트

```powershell
# (1) IMAP/SMTP 로그인 + Gemini API 키까지 한 번에 점검
python worksmail_digest.py --test

# (2) 실제 메일을 모아 요약해보되, 발송은 안 하고 화면에만 출력
python worksmail_digest.py --dry-run --since-hours 48

# (3) 문제 없으면 실제로 한 번 발송
python worksmail_digest.py
```

- `--test` 에서 로그인이 실패하면 → IMAP 허용 여부 / 앱 비밀번호를 다시 확인
- `--dry-run` 결과가 만족스러우면 실제 실행으로 넘어가세요

### 특정 날짜만 지정해서 테스트하기

매일 자동 배치를 기다리지 않고, **원하는 하루치 메일만 바로 요약·발송**해서
확인하고 싶을 때 `--date` 를 씁니다:

```powershell
# 2026-07-15 하루 동안 받은 메일만 요약해서 실제로 발송
python worksmail_digest.py --date 2026-07-15

# 발송 없이 화면에서만 미리 보고 싶다면 --dry-run 을 같이
python worksmail_digest.py --date 2026-07-15 --dry-run
```

- `--date` 는 `state.json`(마지막 실행 시각)을 건드리지 않습니다. 즉 이 테스트를
  아무리 돌려도 다음 날 정규 자동 배치가 놓치는 메일 없이 정상 작동합니다.
- `--since-hours` 와 `--date` 는 동시에 쓸 수 없습니다(둘 다 "어느 기간을 볼지"를
  정하는 옵션이라 하나만 선택).

### 스케줄(취합 간격/발송 시각)이 실제로 맞물려 도는지 미리 보기

```powershell
python worksmail_digest.py --watch-once --dry-run
```
지금이 발송할 때가 아니면 "아직 발송 시각이 아님"이라고만 로그를 남기고 조용히
끝납니다. `config.yaml`의 `schedule.anchor_time`을 지금 시각 근처로 잠깐 바꿔두고
실행해보면 실제로 발송되는지 확인할 수 있습니다.

---

## 6. 자동 실행 등록 (작업 스케줄러)

**중요:** 이제 "몇 시에 보낼지"는 `config.yaml`의 `schedule`(또는 관리자 UI)이 결정합니다.
작업 스케줄러는 그냥 **자주(예: 10분마다) `--watch-once`를 호출**하기만 하면 되고,
스크립트가 알아서 "지금이 보낼 때인지" 판단합니다. 그래서 나중에 관리자 UI에서
발송 시각을 08:00 → 09:00 으로 바꿔도, 작업 스케줄러 등록을 다시 할 필요가 없습니다.

**관리자 권한 PowerShell**에서 아래를 실행하면 10분마다 점검하는 작업이 등록됩니다.
(경로를 변수에 먼저 담아 넘겨야 합니다 — `/TR "\"...\""` 처럼 따옴표를 직접
이스케이프하면 PowerShell이 네이티브 명령에 인자를 전달하는 방식 때문에 따옴표가
깨져서 `잘못된 인수/옵션` 오류가 납니다.)

```powershell
$taskPath = "C:\Users\kimdh\Desktop\worksmail\run_watch_once.bat"
schtasks /Create /SC MINUTE /MO 10 /TN "WorksMail Watch" /TR $taskPath /RL LIMITED /F
```

- 간격을 바꾸려면 `/MO 10`을 원하는 분으로 (너무 촘촘하지 않게 5~15분 권장)
- 등록 확인: `schtasks /Query /TN "WorksMail Watch"`
- 지금 바로 한번 점검해보기: `schtasks /Run /TN "WorksMail Watch"` (발송 시각이 아니면 아무 일도 안 일어나는 게 정상)
- 삭제: `schtasks /Delete /TN "WorksMail Watch" /F`

> PC가 꺼져 있던 동안 지나간 슬롯은 밀어서 몰아 보내지 않고, 켜진 뒤 돌아온
> 첫 점검 때 바로 다음 슬롯 하나만 봅니다 (예: 매일 08:00 설정인데 PC를 사흘 껐다
> 켜도, 사흘치를 한꺼번에 보내지 않고 다음 예정 시각 한 번만 발송).

### (선택) GUI로 더 세밀하게
`Win + R` → `taskschd.msc` → 방금 만든 **WorksMail Watch** 더블클릭 →
**조건/설정** 탭에서:
- "예약된 시작 시간을 놓친 경우 가능한 한 빨리 작업 시작" 체크
- (노트북이면) "컴퓨터의 전원이 배터리인 경우 작업 시작 안 함" 체크 해제

---

## 7. 로그 & 문제 해결

- 실행 기록은 `worksmail.log` 에 쌓입니다. 문제가 생기면 이 파일을 먼저 확인하세요.
- `state.json` 에 마지막 실행 시각이 저장되어, 다음 실행 때 그 이후 메일만 가져옵니다.
  (중복·누락 방지) 처음부터 다시 받고 싶으면 `state.json` 을 삭제하세요.

| 증상 | 확인할 것 |
|------|-----------|
| IMAP 로그인 실패 | 관리자 콘솔 IMAP 허용 여부 / 2단계 인증 계정은 앱 비밀번호 사용 |
| SMTP 발송 실패 | `sender` 계정 비밀번호, 포트 587 방화벽 |
| Gemini 오류 | API 키 유효성, 모델명 오타, 회사 네트워크의 외부 접속 차단 |
| 요약이 비었음 | 해당 시간대에 새 메일이 없었을 수 있음(`--since-hours` 로 확대) |
| `--watch-once`를 계속 돌려도 안 보내짐 | `python worksmail_digest.py --test` 로 "다음 예정 발송 시각"이 언제인지 확인. 그 시각이 지나야 발송됨 |
| 관리자 UI가 안 열림 | 콘솔 창이 닫혀있진 않은지, 다른 프로그램이 5000번 포트를 쓰고 있진 않은지 확인 |

---

## 8. 보안 메모

- `config.yaml`(비밀번호 포함)은 이 PC에만 두고 공유하지 마세요.
- 여러 사람이 쓰는 PC라면 이 폴더 접근 권한을 본인 계정으로 제한하는 것이 좋습니다.
- 앱 비밀번호는 언제든 네이버 웍스에서 폐기·재발급할 수 있습니다.
- 관리자 UI는 `127.0.0.1`(이 PC)에서만 열립니다. 비밀번호는 별개로 걸려있지만,
  이 PC 자체에 접근할 수 있는 사람은 누구나 열어볼 수 있다는 점을 기억하세요.

---

## 9. 다른 PC로 이전하기 (Git 기반)

상시 켜두는 PC를 바꾸거나, 지금 PC에서 새 PC로 옮길 때의 절차입니다. 코드는
**GitHub 저장소**(`https://github.com/ganzyKIM/worksmail_auto`)로 관리하고,
**비밀번호가 든 `config.yaml`만 별도로(USB로만)** 옮기는 방식입니다.

> ⚠️ `config.yaml`·`state.json`·`worksmail.log`는 `.gitignore`에 등록되어 있어
> **git에는 절대 올라가지 않습니다.** 저장소가 공개(public)든 비공개(private)든
> 이 파일들을 임의로 `git add -f` 하지 마세요 — 회사 메일 비밀번호와 Gemini API
> 키가 그대로 노출됩니다.

### 9-1. 옮길 것 / 새로 만들 것

| 항목 | 옮기는 방법 |
|------|-----------|
| 코드 전체 (`.py`, `templates/`, `requirements*.txt`, `*.bat`, `README.md`) | `git clone` (아래 9-3 참고) |
| `config.yaml` (계정 비밀번호, Gemini 키, 관리자 UI 비밀번호 포함) | **반드시 USB로만.** 메일·메신저·클라우드 동기화 폴더 금지, git에도 올리지 않음 |
| `state.json` (마지막 발송/다음 예정 시각) | 옮기면 좋음(선택). 옮기면 스케줄이 끊기지 않고 이어짐. 안 옮겨도 새 PC에서 다음 틱에 자동으로 다시 초기화됨 |
| `.venv`, `__pycache__`, `.claude` | ❌ 옮기지 않음. 새 PC에서 새로 생성 |
| `worksmail.log` | 옮길 필요 없음. 참고용 기록일 뿐 |

### 9-2. 지금 PC에서 할 일 — 코드 최신화 + config 준비

```powershell
cd C:\Users\PC\Desktop\worksmail
git add <바뀐 코드 파일>   # config.yaml/state.json/.venv 는 자동으로 제외됨(.gitignore)
git commit -m "설명"
git push
```

`config.yaml`(과 옮기고 싶으면 `state.json`)만 USB에 복사합니다. 이 두 파일은
**git에 올라가지 않으므로 항상 USB나 다른 안전한 방법으로 직접 옮겨야 합니다.**

### 9-3. 새 PC에서 할 일

1. **Python 설치 확인**: `python --version` (없으면 python.org에서 설치, "Add to PATH" 체크)
2. **저장소 클론**:
   ```powershell
   cd C:\Users\<계정>\Desktop
   git clone https://github.com/ganzyKIM/worksmail_auto.git worksmail
   cd worksmail
   ```
   (처음 클론할 때 GitHub 로그인 창이 뜨면 ganzyKIM 계정으로 로그인)
3. **USB에서 `config.yaml`(과 있다면 `state.json`) 복사** → `worksmail` 폴더 안에 붙여넣기
4. **가상환경 새로 생성**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
5. **연결 확인**:
   ```powershell
   python worksmail_digest.py --test
   ```
   실패하면 새 PC의 네트워크/방화벽이 993·587 포트 아웃바운드를 막고 있는지 확인
6. **관리자 UI로 설정 재확인** (선택): `python admin_ui.py` → http://127.0.0.1:5000 →
   계정·수신자·스케줄이 제대로 옮겨왔는지 훑어보기
7. **작업 스케줄러 등록** (6번 섹션의 `schtasks` 명령 그대로 실행)
8. **다음날(또는 다음 예정 시각) 확인**: 수신자에게 요약 메일이 도착했는지,
   `worksmail.log`에 오류가 없는지 확인

### 9-4. 예전 PC 정리 (중요 — 두 PC 동시 실행 금지)

**새 PC 스케줄러를 켜기 전에 반드시 예전 PC 것부터 꺼야 합니다.** 두 PC 모두
작업 스케줄러가 살아있으면 같은 요약 메일이 두 번 발송됩니다.

- 예전 PC 작업 스케줄러 삭제: `schtasks /Delete /TN "WorksMail Watch" /F`
- 예전 PC에서 `admin_ui.py`가 실행 중이면 콘솔 창을 닫아 종료
- 새 PC에서 정상 동작(7~8번) 확인 후, 예전 PC의 `config.yaml`은 삭제하거나
  최소한 다른 사람이 접근 못 하는 곳으로 이동

### 9-5. 앞으로 코드를 고칠 때

두 PC(또는 개발용 PC)에서 코드를 계속 고친다면, 항상 최신 코드를 받고 시작하세요:

```powershell
git pull
```

`config.yaml`·`state.json`은 git 추적 대상이 아니므로 `git pull` 해도 그대로
유지됩니다. 걱정하지 않아도 됩니다.
