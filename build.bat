@echo off
cd /D "%~dp0"
echo =============================================
echo   Building Cine Scheduler...
echo   Please wait, this takes about 60 seconds.
echo =============================================
echo.
powershell -ExecutionPolicy Bypass -File rebuild.ps1
echo.
echo =============================================
echo   Build process complete.
echo =============================================
echo.
if exist "dist\Cine Scheduler.exe" (
    echo   Result: SUCCESS
) else (
    echo   Result: FAILED - check output above
)
echo.
pause
