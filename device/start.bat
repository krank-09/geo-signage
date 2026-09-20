@echo off
rem Display-laptop launcher (Windows). First run asks 3 questions and saves them to .env.
rem   start.bat            start the display agent
rem   start.bat --reset    forget the saved answers and ask again
setlocal
cd /d "%~dp0"

set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY goto no_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto no_python

if /i "%~1"=="--reset" if exist .env del .env
if exist .env goto have_env

echo First-time setup - the presenter gives you these three values.
set /p SERVER_URL=Server URL (e.g. https://name.trycloudflare.com/api): 
set /p DEVICE_ID=Device ID (e.g. DEV-001): 
set /p REGISTRATION_TOKEN=Registration token (e.g. A1B2-C3D4-E5F6): 
(
  echo SERVER_URL=%SERVER_URL%
  echo DEVICE_ID=%DEVICE_ID%
  echo REGISTRATION_TOKEN=%REGISTRATION_TOKEN%
  echo DISPLAY_PORT=8101
  echo OPEN_BROWSER=1
  echo KIOSK=0
  echo GPS_MODE=sim
  echo ROUTE=chandigarh,delhi,jaipur,mumbai
  echo ROUTE_STEPS=8
  echo ROUTE_DWELL=6
) > .env
echo Saved to .env (run start.bat --reset to change it).
:have_env

if not exist .venv\Scripts\python.exe (
  echo Creating a private Python environment ^(one time^)...
  %PY% -m venv .venv
)
echo Checking dependencies...
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed

echo Starting the display agent. Press Ctrl+C to stop.
.venv\Scripts\python.exe agent.py
goto end

:no_python
echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup, then run this again.
goto end

:failed
echo Installing dependencies failed. Check your internet connection and run this again.

:end
pause
