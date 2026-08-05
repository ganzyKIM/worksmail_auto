@echo off
REM WorksMail 관리자 UI 실행. 더블클릭하면 콘솔창이 뜨고, 안내된 주소를
REM 브라우저에서 열면 됩니다. 이 창을 닫으면 서버가 종료됩니다.
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python admin_ui.py
