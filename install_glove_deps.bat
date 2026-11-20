@echo off
REM Installs pandas + bleak + pyserial for fslRecorder.py into BOTH Pythons on this PC:
REM   1) the global Python 3.11 that VS Code runs   2) the MediaPipe venv
cd /d "%~dp0"
set GLOBALPY=C:\Users\USERUS\AppData\Local\Programs\Python\Python311\python.exe
set VENVPY=MediaPipe\venv\Scripts\python.exe
echo. > install_glove_deps_log.txt
if exist "%GLOBALPY%" (
  echo Installing into global Python 3.11 ...
  "%GLOBALPY%" -m pip install pandas bleak pyserial >> install_glove_deps_log.txt 2>&1
  "%GLOBALPY%" -c "import pandas, serial, bleak; print('OK global: pandas', pandas.__version__, '| pyserial', serial.VERSION, '| bleak installed')" >> install_glove_deps_log.txt 2>&1
)
if exist "%VENVPY%" (
  echo Installing into MediaPipe venv ...
  "%VENVPY%" -m pip install pandas bleak pyserial >> install_glove_deps_log.txt 2>&1
  "%VENVPY%" -c "import pandas, serial, bleak; print('OK venv: pandas', pandas.__version__, '| pyserial', serial.VERSION, '| bleak installed')" >> install_glove_deps_log.txt 2>&1
)
echo.
type install_glove_deps_log.txt | findstr /b "OK"
type install_glove_deps_log.txt | findstr /i "error"
echo.
echo Done. This window closes in 20 seconds.
timeout /t 20
