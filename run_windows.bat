@echo off
rem voice-term launcher for Windows.
rem First run: creates the venv and installs dependencies, then starts the
rem app without a console window (pythonw). Logs go to %LOCALAPPDATA%.

setlocal
cd /d "%~dp0"

set "VENV=.venv"
set "LOGDIR=%LOCALAPPDATA%\voice-term"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

if not exist "%VENV%\Scripts\python.exe" (
    echo [setup] Creating venv and installing dependencies...
    py -3 -m venv "%VENV%" || (echo [error] Python 3 not found. Install it from python.org & pause & exit /b 1)
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt || (echo [error] pip install failed & pause & exit /b 1)
)

rem Launch without a console window; capture output for the tray's "Open log".
powershell -NoProfile -Command ^
  "Start-Process -FilePath '%CD%\%VENV%\Scripts\pythonw.exe' -ArgumentList 'voice_term.py' -WorkingDirectory '%CD%' -RedirectStandardOutput '%LOGDIR%\voice-term.log' -RedirectStandardError '%LOGDIR%\voice-term.err.log'"
endlocal
