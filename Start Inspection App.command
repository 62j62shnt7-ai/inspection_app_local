#!/bin/bash
cd "$(dirname "$0")" || exit 1
export PYTHONHOME="$PWD/runtime/mac"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
PYTHON="$PYTHONHOME/Resources/Python.app/Contents/MacOS/Python"
if [ ! -x "$PYTHON" ]; then
  printf 'The bundled macOS runtime is missing. Please extract the complete app folder.\n'
  read -r -p 'Press Enter to close.'
  exit 1
fi
"$PYTHON" app.py
status=$?
if [ "$status" -ne 0 ]; then
  printf '\nThe app could not start. Check the error above.\n'
  read -r -p 'Press Enter to close.'
fi
exit "$status"
