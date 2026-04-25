import sys
import os
import subprocess

# Force output to a log file since console stdout seems broken
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_log.txt')
log = open(log_path, 'w', encoding='utf-8')

def msg(text):
    log.write(text + '\n')
    log.flush()
    # Also try stderr which might work on console
    sys.stderr.write(text + '\n')
    sys.stderr.flush()

msg("=== Build Script Started ===")
msg(f"Python: {sys.executable}")
msg(f"Version: {sys.version}")
msg(f"CWD: {os.getcwd()}")

# Check files exist
html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Showtime-Manager-v29.html')
launcher_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'launcher.py')
msg(f"HTML exists: {os.path.exists(html_file)}")
msg(f"Launcher exists: {os.path.exists(launcher_file)}")

try:
    import PyInstaller
    msg(f"PyInstaller version: {PyInstaller.__version__}")
except ImportError:
    msg("ERROR: PyInstaller not installed! Installing now...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
    msg("PyInstaller installed successfully.")

# Change to script directory
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
msg(f"Working dir: {script_dir}")

# Run PyInstaller
msg("\n=== Starting PyInstaller Build ===")
cmd = [
    sys.executable, '-m', 'PyInstaller',
    '--onefile', '--noconsole',
    '--name', 'Cine Scheduler',
    '--add-data', f'Showtime-Manager-v29.html{os.pathsep}.',
    'launcher.py',
    '--distpath', 'dist',
    '--workpath', 'build',
    '--noconfirm'
]
msg(f"Command: {' '.join(cmd)}")

result = subprocess.run(cmd, capture_output=True, text=True, cwd=script_dir)
msg(f"\nSTDOUT:\n{result.stdout}")
msg(f"\nSTDERR:\n{result.stderr}")
msg(f"\nReturn code: {result.returncode}")

# Check result
exe_path = os.path.join(script_dir, 'dist', 'Cine Scheduler.exe')
if os.path.exists(exe_path):
    import shutil
    dest = os.path.join(script_dir, 'Cine Scheduler.exe')
    shutil.copy2(exe_path, dest)
    size_mb = os.path.getsize(dest) / (1024*1024)
    msg(f"\n*** SUCCESS! Cine Scheduler.exe created ({size_mb:.1f} MB) ***")
else:
    msg("\n*** BUILD FAILED - no exe produced ***")

log.close()
