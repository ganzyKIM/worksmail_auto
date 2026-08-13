<#
WorksMail 원클릭 설치 스크립트.
WorksMailSetup.exe(IExpress 자가압축 실행파일)가 이 스크립트와 프로젝트 파일들을
임시 폴더에 함께 풀어놓고 이 스크립트를 실행한다. $PSScriptRoot 가 그 임시 폴더(=페이로드 원본).

사람이 더블클릭해서 쓸 때는 파라미터 없이 실행 -> GUI(폴더 선택창, 안내 메시지박스)로 진행.
테스트/자동화용으로 -InstallDir 와 -Silent 를 지원한다 (GUI 없이 지정 경로에 설치).
#>
param(
    [string]$InstallDir = "",
    [switch]$Silent
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Info($msg, $title = "WorksMail 설치") {
    if (-not $Silent) {
        [System.Windows.Forms.MessageBox]::Show($msg, $title, 'OK', 'Information') | Out-Null
    }
    Write-Host $msg
}
function Warn($msg, $title = "WorksMail 설치") {
    if (-not $Silent) {
        [System.Windows.Forms.MessageBox]::Show($msg, $title, 'OK', 'Warning') | Out-Null
    }
    Write-Warning $msg
}
function Fail($msg, $title = "WorksMail 설치 오류") {
    if (-not $Silent) {
        [System.Windows.Forms.MessageBox]::Show($msg, $title, 'OK', 'Error') | Out-Null
    }
    Write-Error $msg
    exit 1
}

Write-Host "================================================"
Write-Host " WorksMail 공용메일 요약봇 - 원클릭 설치"
Write-Host "================================================"

# ── 1) Python 확인 ──────────────────────────────────────────
$pythonOk = $false
try {
    $null = & python --version 2>&1
    if ($LASTEXITCODE -eq 0) { $pythonOk = $true }
} catch { $pythonOk = $false }

if (-not $pythonOk) {
    if (-not $Silent) {
        $result = [System.Windows.Forms.MessageBox]::Show(
            "이 PC에 Python이 설치되어 있지 않은 것 같아요.`n`n지금 Python 다운로드 페이지를 열어드릴까요?`n(설치할 때 'Add python.exe to PATH' 체크 꼭 해주세요. 설치가 끝나면 이 설치 프로그램을 다시 실행하시면 됩니다.)",
            "Python이 필요해요", 'YesNo', 'Warning')
        if ($result -eq 'Yes') { Start-Process "https://www.python.org/downloads/" }
    }
    Fail "Python 미설치로 설치를 중단합니다. Python 설치 후 다시 실행해주세요."
}

# ── 2) 설치 경로 결정 ────────────────────────────────────────
if (-not $InstallDir) {
    $folderDialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $folderDialog.Description = "WorksMail을 설치할 위치를 골라주세요 (이 폴더 안에 'worksmail' 폴더가 만들어져요)"
    $folderDialog.SelectedPath = [Environment]::GetFolderPath('Desktop')
    if ($folderDialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        Fail "설치가 취소되었습니다."
    }
    $InstallDir = Join-Path $folderDialog.SelectedPath "worksmail"
}

if (Test-Path $InstallDir) {
    if (-not $Silent) {
        $overwrite = [System.Windows.Forms.MessageBox]::Show(
            "폴더가 이미 있어요:`n$InstallDir`n`n계속 진행하면 코드 파일은 최신 버전으로 덮어쓰고,`nconfig.yaml(계정 정보)은 그대로 보존합니다. 계속할까요?",
            "폴더가 이미 있어요", 'YesNo', 'Warning')
        if ($overwrite -ne 'Yes') { Fail "설치가 취소되었습니다." }
    }
} else {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

Write-Host "설치 위치: $InstallDir"

# ── 3) 페이로드(zip) 압축 해제 (config.yaml/state.json/기존 .venv는 zip에 없으므로 보존됨) ──
# 주의: IExpress(.SED)는 하위 폴더 구조를 보존하지 못하고 파일을 평평하게 풀어버리는
# 문제가 있어(실측 확인됨), templates/static 처럼 서브폴더가 있는 프로젝트는 통째로
# zip 하나로 패키징한 뒤 여기서 직접 압축을 풀어야 폴더 구조가 살아남는다.
Write-Host "[1/5] 파일 압축 해제 중..."
$zipPath = Join-Path $PSScriptRoot "payload.zip"
if (-not (Test-Path $zipPath)) {
    Fail "payload.zip을 찾을 수 없습니다 (설치 파일이 손상되었을 수 있어요): $zipPath"
}
Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force

Push-Location $InstallDir
try {
    # ── 4) 가상환경 + 패키지 설치 ──────────────────────────────
    if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
        Write-Host "[2/5] 파이썬 가상환경 생성 중..."
        & python -m venv .venv
    } else {
        Write-Host "[2/5] 기존 가상환경을 재사용합니다."
    }
    if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
        Fail "가상환경 생성에 실패했습니다."
    }

    Write-Host "[3/5] 필요한 패키지 설치 중... (몇 분 걸릴 수 있어요)"
    & ".\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    & ".\.venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
    & ".\.venv\Scripts\python.exe" -m pip install --quiet -r requirements-dev.txt

    # ── 5) config.yaml 부트스트랩 ──────────────────────────────
    if (-not (Test-Path ".\config.yaml")) {
        Copy-Item ".\config.example.yaml" ".\config.yaml"
        Write-Host "config.yaml 기본 틀을 만들었어요 (계정/수신자는 브라우저에서 입력)."
    } else {
        Write-Host "기존 config.yaml을 그대로 사용합니다."
    }

    # ── 6) 작업 스케줄러 등록 ──────────────────────────────────
    # 주의: 네이티브 exe(schtasks)의 stderr를 PowerShell에서 리다이렉트(2>)하면
    # $ErrorActionPreference='Stop' 아래서 정상 실행조차 종료 오류로 처리되는 경우가
    # 있어, try/catch로 감싸고 리다이렉트는 최소화한다.
    Write-Host "[4/5] 자동 실행(작업 스케줄러) 등록 중..."
    $taskPath = Join-Path $InstallDir "run_watch_once.bat"
    if (Get-ScheduledTask -TaskName "WorksMail Watch" -ErrorAction SilentlyContinue) {
        try { schtasks /Delete /TN "WorksMail Watch" /F | Out-Null } catch { }
    }

    $created = ""
    $taskOk = $true
    try {
        $created = schtasks /Create /SC MINUTE /MO 10 /TN "WorksMail Watch" /TR $taskPath /RL LIMITED /F 2>&1
        if ($LASTEXITCODE -ne 0) { $taskOk = $false }
    } catch {
        $taskOk = $false
        $created = $_.Exception.Message
    }
    if (-not $taskOk) {
        Warn "작업 스케줄러 등록에 실패했습니다 (관리자 권한으로 설치 프로그램을 다시 실행해보세요):`n$created"
    }

    # ── 7) 관리자 UI 실행 + 안내 페이지 열기 ───────────────────
    Write-Host "[5/5] 관리자 화면을 여는 중..."
    if (-not $Silent) {
        Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "admin_ui.py" -WindowStyle Minimized
        $ready = $false
        for ($i = 0; $i -lt 10; $i++) {
            Start-Sleep -Seconds 1
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:5000" -UseBasicParsing -TimeoutSec 2
                $ready = $true
                break
            } catch { }
        }
        Start-Process "http://127.0.0.1:5000"
        Start-Process (Join-Path $InstallDir "SETUP_GUIDE.html")
    }

    Write-Host "================================================"
    Write-Host " 설치 완료! -> $InstallDir"
    Write-Host "================================================"

    if (-not $Silent) {
        Info "설치가 끝났어요!`n`n설치 위치:`n$InstallDir`n`n브라우저와 안내 페이지가 자동으로 열렸어요.`n안내 페이지의 순서대로 계정 정보를 입력해주세요."
    }
} finally {
    Pop-Location
}
