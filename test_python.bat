@echo off
"C:\Users\jkalsi\AppData\Local\Programs\Python\Python314\python.exe" -c "print('PYTHON_OK')" > python_test.txt 2>&1
echo EXIT=%ERRORLEVEL% >> python_test.txt
