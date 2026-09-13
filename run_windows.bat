@echo off
rem voice-term launcher for Windows.
rem First run: creates the venv and installs dependencies, then starts the
rem app without a console window (pythonw). Logs go to %LOCALAPPDATA%.
rem Python is located via uv (preferred), the py launcher, or python on PATH.
rem A venv whose base interpreter has disappeared (e.g. Python was
rem uninstalled or the repo was moved) is detected and rebuilt automatically.

setlocal
cd /d "%~dp0"

set "VENV=.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "LOGDIR=%LOCALAPPDATA%\voice-term"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem Reuse the venv only if it runs and has the dependencies installed.
if not exist "%VPY%" goto :setup
"%VPY%" -c "import faster_whisper, sounddevice, pynput, pystray" >nul 2>&1 && goto :launch
echo [setup] Existing venv is broken or incomplete. Rebuilding...
rmdir /s /q "%VENV%"

:setup
call :create_venv
if errorlevel 1 (
    echo [error] Setup failed. Install uv or Python 3.11+ and try again.
    pause
    exit /b 1
)

:launch
rem Launch without a console window; capture output for the tray's "Open log".
powershell -NoProfile -Command ^
  "Start-Process -FilePath '%CD%\%VENV%\Scripts\pythonw.exe' -ArgumentList 'voice_term.py' -WorkingDirectory '%CD%' -RedirectStandardOutput '%LOGDIR%\voice-term.log' -RedirectStandardError '%LOGDIR%\voice-term.err.log'"
endlocal
exit /b 0

rem ---------------------------------------------------------------------------
:create_venv
rem Prefer uv: it can also fetch the Python interpreter itself.
where uv >nul 2>&1
if not errorlevel 1 (
    echo [setup] Creating venv with uv - Python 3.12...
    uv venv --python 3.12 "%VENV%" || exit /b 1
    uv pip install --python "%VPY%" -r requirements.txt || exit /b 1
    exit /b 0
)

rem Then the py launcher, then python on PATH (the Store stub fails the -c check).
set "BASEPY="
where py >nul 2>&1
if not errorlevel 1 set "BASEPY=py -3"
if not defined BASEPY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "BASEPY=python"
)
if not defined BASEPY (
    echo [error] No usable Python found - need uv, the py launcher, or Python 3.11+ on PATH.
    exit /b 1
)

echo [setup] Creating venv with %BASEPY% and installing dependencies...
%BASEPY% -m venv "%VENV%" || exit /b 1
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r requirements.txt || exit /b 1
exit /b 0
