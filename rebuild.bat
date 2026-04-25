@echo off
cd /d "C:\Users\jkalsi\OneDrive - Cinepolis\Desktop\New HTML SCHEUDLER\ANTIGRAVITY"
"C:\Users\jkalsi\AppData\Local\Programs\Python\Python314\python.exe" -m PyInstaller --onefile --noconsole --name "Cine Scheduler" --add-data "Showtime-Manager-v29.html;." launcher.py --distpath dist --workpath build --noconfirm > build_log.txt 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> build_log.txt
if exist "dist\Cine Scheduler.exe" (
    copy /Y "dist\Cine Scheduler.exe" "Cine Scheduler.exe"
    echo COPY_OK >> build_log.txt
) else (
    echo NO_EXE_FOUND >> build_log.txt
)
