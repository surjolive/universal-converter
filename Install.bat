@echo off
setlocal
cd /d "%~dp0"
py -3.12 -m venv .venv 2>nul
if not exist ".venv\Scripts\python.exe" py -3.13 -m venv .venv
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if not exist ".venv\Scripts\python.exe" (
	echo Python 3.12 or newer was not found. Install Python and enable the py launcher.
	pause
	exit /b 1
)
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if errorlevel 1 (
	echo Python 3.12 or newer is required.
	pause
	exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
call Check-Dependencies.bat
