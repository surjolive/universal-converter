@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
	echo Python environment not found. Run Install.bat first.
	pause
	exit /b 1
)

echo Installing build dependencies...
"%PYTHON%" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto failed

echo Building the desktop application...
"%PYTHON%" -m PyInstaller --noconfirm --clean --onedir --windowed --icon "%CD%\images\universal_converter.ico" --name "UniversalConverter" --add-data "%CD%\frontend;frontend" --add-data "%CD%\images;images" --collect-all webview --collect-all uvicorn --collect-all fastapi --collect-all sqlalchemy --collect-all PIL --collect-all reportlab --collect-all fitz --collect-all docx --collect-all openpyxl --collect-all cairosvg --collect-all yaml --workpath "build\pyinstaller-app" --specpath "build\spec-app" --distpath "dist" scripts\desktop.py
if errorlevel 1 goto failed

echo Building the setup wizard...
"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --icon "%CD%\images\universal_converter.ico" --name "Universal-Converter-Setup" --add-data "%CD%\dist\UniversalConverter;app" --add-data "%CD%\images\universal_converter.ico;images" --workpath "build\pyinstaller-setup" --specpath "build\spec-setup" --distpath "dist" setup_installer.py
if errorlevel 1 goto failed

echo.
echo Setup executable created:
echo %~dp0dist\Universal-Converter-Setup.exe
pause
exit /b 0

:failed
echo.
echo Build failed. Review the error above.
pause
exit /b 1
