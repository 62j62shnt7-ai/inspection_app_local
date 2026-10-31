@echo off
setlocal
cd /d "%~dp0"
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
if not exist "%~dp0runtime\windows\python.exe" (
  echo The bundled Windows runtime is missing. Please extract the complete app folder.
  pause
  exit /b 1
)
"%~dp0runtime\windows\python.exe" "%~dp0app.py"
if errorlevel 1 (
  echo The app could not start. Check the error above.
  pause
  exit /b 1
)
endlocal
