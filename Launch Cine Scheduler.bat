@echo off
cd /D "%~dp0"
echo =============================================
echo   Launching Cine Scheduler with latest UI...
echo =============================================
echo.

REM Step 1: Pre-copy the updated HTML to AppData BEFORE the exe runs
set "APPDATA_DIR=%APPDATA%\ShowtimeManager"
if not exist "%APPDATA_DIR%" mkdir "%APPDATA_DIR%"
copy /y "Showtime-Manager-v29.html" "%APPDATA_DIR%\index.html" >nul 2>&1
echo [OK] Updated HTML copied to AppData.

REM Step 2: Start the exe  
echo [OK] Starting Cine Scheduler...
start "" "Cine Scheduler.exe"

REM Step 3: Wait for the exe to overwrite with its old bundled copy, then overwrite again
timeout /t 3 /nobreak >nul
copy /y "Showtime-Manager-v29.html" "%APPDATA_DIR%\index.html" >nul 2>&1
echo [OK] Latest UI applied!
echo.
echo Cine Scheduler is running with the latest changes.
echo You can close this window.
timeout /t 5
