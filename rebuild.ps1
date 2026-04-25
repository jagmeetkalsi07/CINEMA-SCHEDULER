Set-Location "C:\Users\jkalsi\OneDrive - Cinepolis\Desktop\New HTML SCHEUDLER\ANTIGRAVITY"

# Clean old builds
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "Cine Scheduler.spec") { Remove-Item -Force "Cine Scheduler.spec" }

Write-Host "Starting PyInstaller build..." -ForegroundColor Cyan

$proc = Start-Process -FilePath "C:\Users\jkalsi\AppData\Local\Programs\Python\Python314\Scripts\pyinstaller.exe" `
    -ArgumentList '--onefile','--noconsole','--name','Cine Scheduler','--add-data','Showtime-Manager-v29.html;.','launcher.py','--distpath','dist','--workpath','build','--noconfirm' `
    -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput build_stdout.txt `
    -RedirectStandardError build_stderr.txt

"EXIT=$($proc.ExitCode)" | Out-File build_status.txt -Encoding ascii

if (Test-Path "dist\Cine Scheduler.exe") {
    Copy-Item "dist\Cine Scheduler.exe" "Cine Scheduler.exe" -Force
    Write-Host "SUCCESS! Cine Scheduler.exe has been updated!" -ForegroundColor Green
    "COPY_OK" | Add-Content build_status.txt -Encoding ascii
} else {
    Write-Host "BUILD FAILED. Check build_stdout.txt and build_stderr.txt" -ForegroundColor Red
    if (Test-Path "build_stdout.txt") {
        Write-Host "`n--- STDOUT ---" -ForegroundColor Yellow
        Get-Content build_stdout.txt -Tail 30
    }
    if (Test-Path "build_stderr.txt") {
        Write-Host "`n--- STDERR ---" -ForegroundColor Yellow
        Get-Content build_stderr.txt -Tail 30
    }
}
