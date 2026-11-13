@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
  echo Cannot access the app folder. Extract it to a writable local folder.
  pause
  exit /b 1
)
if not exist "%~dp0runtime\windows\.embedded-runtime" goto setup_runtime
if not exist "%~dp0runtime\windows\python.exe" goto setup_runtime
if not exist "%~dp0runtime\windows\Lib\site-packages\openpyxl" goto setup_runtime
if not exist "%~dp0runtime\windows\Lib\site-packages\et_xmlfile" goto setup_runtime
goto start_app

:setup_runtime
  echo The Windows runtime or a spreadsheet dependency is missing. Setting it up...
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap_windows.ps1"
  if errorlevel 1 (
    echo First-run setup failed. Check the message above and try again.
    pause
    exit /b 1
  )

:start_app
if not exist "%~dp0runtime\windows\python.exe" (
  echo Setup finished without creating the Windows Python runtime.
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
