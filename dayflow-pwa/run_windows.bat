@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo First run setup_windows.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
uvicorn app.main:app --host 0.0.0.0 --port 8000
