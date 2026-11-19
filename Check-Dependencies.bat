@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -c "import fastapi, sqlalchemy, PIL, reportlab, openpyxl; print('Python dependencies: OK')"
where ffmpeg >nul 2>&1 && echo FFmpeg: available || echo FFmpeg: missing
where soffice >nul 2>&1 && echo LibreOffice: available || echo LibreOffice: missing
where php >nul 2>&1 && echo PHP: available || echo PHP: missing
where node >nul 2>&1 && echo Node.js: available || echo Node.js: missing
