@echo off
REM 지금 바로 즉시 수집·요약·발송 (스케줄 무시). 수동 확인용.
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python worksmail_digest.py
