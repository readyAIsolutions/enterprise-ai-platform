@echo off
REM ===========================================================================
REM  ENI ENTERPRISE — Boot All Servers (Windows)
REM ===========================================================================
REM  Starts every server the ENI Enterprise Platform needs to run:
REM    1. Multiplayer coordination server   (WebSocket :8787 + HTTP :8788)
REM    2. Local one-prompt->program brain   (HTTP :8913)
REM    3. (optional) Free Model Router      (HTTP :8920) if present
REM  Also offers to start a builder client and seed the skills pack.
REM
REM  Usage:
REM    boot_all (or boot_all.bat)      - interactive
REM    boot_all --headless             - start servers in background, no prompts
REM ===========================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "VENV=%~dp0venv"
set "PY=python"
if exist "%VENV%\Scripts\python.exe" set "PY=%VENV%\Scripts\python.exe"

echo.
echo  ==============================================
echo    ENI ENTERPRISE — Server Boot
echo  ==============================================
echo.

REM ---- 1. Multiplayer coordination server :8787 ----
echo  [1/3] Starting Multiplayer coordination server (ws://0.0.0.0:8787)...
start "ENI-Multiplayer" /b "%PY%" -m enterprise.multiplayer.server.server 8787
echo         ok

REM ---- 2. Local controller :8913 ----
echo  [2/3] Starting Local one-prompt controller (http://127.0.0.1:8913)...
start "ENI-Controller" /b "%PY%" -m enterprise.local_controller.controller --port 8913
echo         ok

REM ---- 3. Free model router :8920 (optional) ----
set "ROUTER=%USERPROFILE%\.hermes\scripts\free_router.py"
if exist "%ROUTER%" (
  echo  [3/3] Starting Free Model Router (http://127.0.0.1:8920)...
  start "ENI-FreeRouter" /b "%PY%" "%ROUTER%" --port 8920
  echo         ok
) else (
  echo  [3/3] Free Model Router not found - skipping.
)

echo.
echo  All servers launched. Dashboard endpoints:
echo    health  http://127.0.0.1:8788/health
echo    board   http://127.0.0.1:8788/api/board
echo    brains  http://127.0.0.1:8913/health
echo.
choice /C YN /M "Start a local builder client too (llm worker)? "
if errorlevel 2 goto :done
echo  Starting builder client...
start "ENI-Builder" /b "%PY%" -m enterprise.multiplayer.client.client --worker llm --host 127.0.0.1 --port 8787
:done
echo.
echo  Done. Tip:  python scripts\eni_cli status   to verify the platform.
pause
endlocal