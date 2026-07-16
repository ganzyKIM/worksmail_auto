@echo off
REM 네이버 웍스 공용계정 일일 메일 요약 실행 스크립트 (작업 스케줄러가 이 파일을 호출)
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python worksmail_digest.py
