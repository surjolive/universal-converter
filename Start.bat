@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  start "Universal Converter" ".venv\Scripts\python.exe" -m backend.main
) else (
  start "Universal Converter" python -m backend.main
)
start "" "http://127.0.0.1:8765"
