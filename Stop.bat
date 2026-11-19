@echo off
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*backend.main*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
