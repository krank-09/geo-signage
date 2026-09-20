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

if /i "%~1"=="--reset" (
  if exist .env del .env
  if exist .cache\identity.json del .cache\identity.json
  if exist .cache\discovery_secret del .cache\discovery_secret
)
if exist .env goto have_env

echo First-time setup - the presenter gives you the first three values.
set /p SERVER_URL=Server URL (e.g. https://name.trycloudflare.com/api): 
echo Device ID and token: type them if the presenter gave them, or just press Enter to let the dashboard find this display.
set DEVICE_ID=
set REGISTRATION_TOKEN=
set /p DEVICE_ID=Device ID (e.g. DEV-001, or Enter to be found automatically): 
if "%DEVICE_ID%"=="" goto skip_token
set /p REGISTRATION_TOKEN=Registration token (e.g. A1B2-C3D4-E5F6): 
:skip_token
echo.
echo Laptops have no GPS, so this display uses a simulated position.
echo In the demo one display drives a route and the others stay put. Ask the presenter which this one is.
set /p MOVES=Should this display MOVE along a route? (y/N): 
if /i "%MOVES%"=="y" goto write_moving
set /p PLACE=Which place is it in? (chandigarh, delhi, jaipur, mumbai, ahmedabad) [delhi]: 
if "%PLACE%"=="" set PLACE=delhi
(
  echo SERVER_URL=%SERVER_URL%
  echo DEVICE_ID=%DEVICE_ID%
  echo REGISTRATION_TOKEN=%REGISTRATION_TOKEN%
  echo DISPLAY_PORT=8101
  echo OPEN_BROWSER=1
  echo KIOSK=0
  echo DEMO_CONTROLS=1
  echo GPS_MODE=fixed
  echo PLACE=%PLACE%
) > .env
goto env_written
:write_moving
(
  echo SERVER_URL=%SERVER_URL%
  echo DEVICE_ID=%DEVICE_ID%
  echo REGISTRATION_TOKEN=%REGISTRATION_TOKEN%
  echo DISPLAY_PORT=8101
  echo OPEN_BROWSER=1
  echo KIOSK=0
  echo DEMO_CONTROLS=1
  echo GPS_MODE=sim
  echo ROUTE=chandigarh,delhi,jaipur,mumbai
  echo ROUTE_STEPS=8
  echo ROUTE_DWELL=6
) > .env
:env_written
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
