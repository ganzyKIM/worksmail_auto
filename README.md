# 네이버 웍스 공용계정 일일 메일 요약

info·base 같은 **공용 업무 계정**의 받은 메일을 매일 자동으로 모아, 제미나이(Gemini)로
요약·중요도 분류한 뒤 개인 계정(kimdh@dobedub.com)으로 보내주는 프로그램입니다.

```
매일 정해진 시각
  → IMAP으로 각 공용계정의 '새 메일' 수집 (읽음 표시는 안 건드림)
  → Gemini API로 계정별 요약 + 중요도/분류/필요조치 정리
  → SMTP로 개인계정에 요약 메일 발송
```

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

기본 모델은 `gemini-2.5-flash`(빠르고 저렴)입니다. 더 정교한 요약을 원하면
`gemini-2.5-pro` 로 바꾸세요.

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

`config.example.yaml` 을 복사해서 `config.yaml` 을 만들고 값을 채웁니다:

```powershell
Copy-Item config.example.yaml config.yaml
notepad config.yaml
```

- `accounts`: 수집할 공용계정들 (이름/이메일/비밀번호). 필요한 만큼 추가
- `sender`: 요약 메일을 **보낼 때** 쓸 계정 (공용계정 중 하나여도 됨)
- `recipient`: 요약을 **받을** 개인 메일 (이미 `kimdh@dobedub.com` 으로 채워져 있음)
- `gemini.api_key`: 제미나이 키

> ⚠️ `config.yaml` 에는 비밀번호가 들어갑니다. 외부에 공유하거나 클라우드에 올리지 마세요.

---

## 4-1. (개발자용) 자동 테스트

핵심 로직(제목 디코딩, 본문 추출, 날짜 처리, 프롬프트 생성, 설정 검증 등)은
실제 메일 서버 없이도 pytest로 검증됩니다. 코드를 수정했다면 실행해보세요:

```powershell
pip install -r requirements-dev.txt
pytest -v
```

---

## 5. 동작 테스트

```powershell
# (1) IMAP/SMTP 로그인이 되는지만 점검
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

---

## 6. 매일 자동 실행 등록 (작업 스케줄러)

가장 쉬운 방법 — **관리자 권한 PowerShell**에서 아래 한 줄을 실행하면
매일 아침 **08:00**에 자동 실행되는 작업이 등록됩니다:

```powershell
schtasks /Create /SC DAILY /TN "WorksMail Digest" /TR "\"C:\Users\kimdh\Desktop\worksmail\run.bat\"" /ST 08:00 /RL LIMITED /F
```

- 시간 바꾸려면 `/ST 08:00` 을 원하는 시각으로 (예: `/ST 07:30`)
- 등록 확인: `schtasks /Query /TN "WorksMail Digest"`
- 지금 바로 한번 돌려보기: `schtasks /Run /TN "WorksMail Digest"`
- 삭제: `schtasks /Delete /TN "WorksMail Digest" /F`

> PC가 꺼져 있으면 그 시각엔 실행되지 않습니다. 상시 켜두거나, 켜진 직후
> 놓친 작업을 실행하도록 아래 GUI 옵션을 켜세요.

### (선택) GUI로 더 세밀하게
`Win + R` → `taskschd.msc` → 방금 만든 **WorksMail Digest** 더블클릭 →
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

---

## 8. 보안 메모

- `config.yaml`(비밀번호 포함)은 이 PC에만 두고 공유하지 마세요.
- 여러 사람이 쓰는 PC라면 이 폴더 접근 권한을 본인 계정으로 제한하는 것이 좋습니다.
- 앱 비밀번호는 언제든 네이버 웍스에서 폐기·재발급할 수 있습니다.
