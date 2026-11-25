@echo off
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" main.py
if errorlevel 1 (
  echo.
  echo === 실행 실패 ===
  pause
)
