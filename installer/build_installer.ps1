<#
WorksMailSetup.exe 빌드 스크립트.

프로젝트 전체를 zip 하나(payload.zip)로 묶고, install.ps1과 함께 Windows 내장
도구 iexpress.exe로 자가압축 설치 실행파일 하나로 만든다. 외부 도구(7-Zip,
Inno Setup 등) 설치 없이 이 PC에서 바로 빌드 가능.

※ zip을 쓰는 이유: IExpress(.SED)는 하위 폴더가 있는 파일들을 개별로 나열해서
넣으면 압축 해제 시 폴더 구조를 보존하지 못하고 평평하게(flat) 풀어버리는
문제가 실측 확인됨 (templates/, static/fonts/ 같은 서브폴더가 사라짐).
그래서 프로젝트를 zip으로 통째로 묶어 "파일 1개"로 다루고, install.ps1이
Expand-Archive로 직접 풀어서 폴더 구조를 살린다.

사용법: powershell -File installer\build_installer.ps1
결과물: dist\WorksMailSetup.exe

-TestArgs 를 주면(예: '-InstallDir C:\test -Silent') 그 인자를 AppLaunched에
그대로 박아서 빌드한다 — IExpress로 만든 exe는 실행할 때 준 커맨드라인 인자를
내부 프로그램에 자동으로 넘겨주지 않기 때문에(SED에 고정), 자동화 테스트를
하려면 이렇게 테스트 전용으로 다시 빌드해야 한다. 실제 배포판은 이 옵션 없이
빌드해서 install.ps1이 인자 없이 실행 -> GUI로 동작하게 한다.
#>
param(
    [string]$TestArgs = ""
)
$ErrorActionPreference = "Stop"

$installerDir = $PSScriptRoot
$root = Split-Path -Parent $installerDir
$distDir = Join-Path $root "dist"
$targetExe = Join-Path $distDir "WorksMailSetup.exe"
$zipPath = Join-Path $installerDir "payload.zip"
$sedPath = Join-Path $installerDir "worksmail.sed"

if (-not (Test-Path $distDir)) { New-Item -ItemType Directory -Path $distDir | Out-Null }
if (Test-Path $targetExe) { Remove-Item $targetExe -Force }
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Write-Host "[1/3] 배포용 zip 만드는 중..."
$excludeTop = @('.git', '.venv', '__pycache__', '.pytest_cache', 'installer', 'dist',
                'config.yaml', 'state.json', 'worksmail.log')
$items = Get-ChildItem -Path $root -Force | Where-Object { $excludeTop -notcontains $_.Name }
Compress-Archive -Path ($items.FullName) -DestinationPath $zipPath -Force
$zipSize = (Get-Item $zipPath).Length
Write-Host "  -> $zipPath ($('{0:N0}' -f $zipSize) bytes)"

Write-Host "[2/3] .SED 생성 중..."
$sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles

[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=$targetExe
FriendlyName=WorksMail 원클릭 설치
AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Normal -File install.ps1 $TestArgs
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
FILE0=install.ps1
FILE1=payload.zip

[SourceFiles]
SourceFiles0=$installerDir\

[SourceFiles0]
%FILE0%=
%FILE1%=
"@

# iexpress.exe는 .SED를 시스템 ANSI 코드페이지(한국어 Windows면 CP949) 기준으로
# 읽으므로 그 인코딩으로 저장한다 (UTF-8로 저장하면 FriendlyName 등 한글이 깨짐).
[System.IO.File]::WriteAllText($sedPath, $sed, [System.Text.Encoding]::Default)

Write-Host "[3/3] iexpress로 빌드 중..."
# iexpress.exe는 GUI 앱이라 '&'로 그냥 부르면 끝나기 전에 다음 줄로 넘어가버린다 ->
# -Wait 로 완료까지 대기. 경로는 -ArgumentList 배열 원소로 넘겨야 안전하다
# (수동으로 "..." 이스케이프를 문자열에 넣으면 PowerShell이 네이티브 exe에 인자
# 전달할 때 깨지는 문제가 있음 — 실측 확인됨).
$proc = Start-Process -FilePath "iexpress" -ArgumentList "/N", "/Q", $sedPath -Wait -NoNewWindow -PassThru
if ($proc.ExitCode -ne 0) {
    Write-Error "iexpress 실행 실패 (종료코드 $($proc.ExitCode))"
    exit 1
}

Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Remove-Item $sedPath -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $installerDir -Filter "*.DDF" -ErrorAction SilentlyContinue | Remove-Item -Force

if (Test-Path $targetExe) {
    $sizeMb = "{0:N1}" -f ((Get-Item $targetExe).Length / 1MB)
    Write-Host "`n빌드 성공: $targetExe ($sizeMb MB)"
} else {
    Write-Error "빌드 실패: $targetExe 가 생성되지 않았습니다."
    exit 1
}
