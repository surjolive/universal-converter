@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  start "UNIVERSAL CONVERTER" ".venv\Scripts\python.exe" -m backend.main
) else (
  start "UNIVERSAL CONVERTER" python -m backend.main
)
start "" "http://127.0.0.1:8765"
