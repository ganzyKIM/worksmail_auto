@echo off
REM 작업 스케줄러가 이 파일을 자주(예: 10분마다) 호출한다.
REM config.yaml의 schedule(취합 간격/발송 시각)에 따라 "지금이 보낼 때"일 때만 발송한다.
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python worksmail_digest.py --watch-once
