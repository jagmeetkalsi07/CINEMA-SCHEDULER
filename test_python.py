import sys, os
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pytest_result.txt'), 'w') as f:
    f.write(f"Python works!\nVersion: {sys.version}\nExecutable: {sys.executable}\n")
    try:
        import PyInstaller
        f.write(f"PyInstaller: {PyInstaller.__version__}\n")
    except:
        f.write("PyInstaller: NOT AVAILABLE\n")
