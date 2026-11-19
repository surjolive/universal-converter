@echo off
setlocal
cd /d "%~dp0"
if exist "Stop.bat" call Stop.bat
if exist ".venv" rmdir /s /q ".venv"
echo UNIVERSAL CONVERTER runtime removed.
