@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
  echo Cannot access the app folder. Extract it to a writable local folder.
  pause
  exit /b 1
)
if not exist "%~dp0runtime\windows\python.exe" (
  echo The bundled Windows runtime is missing. Please extract the complete app folder.
  pause
  exit /b 1
)
"%~dp0runtime\windows\python.exe" -I -B -X utf8 "%~dp0app.py" %*
if errorlevel 1 (
  echo The app could not start. Check the error above.
  pause
  exit /b 1
)
popd
endlocal
