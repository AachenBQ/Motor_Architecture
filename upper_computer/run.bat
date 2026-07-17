@echo off
setlocal
cd /d "%~dp0"

python -c "import sys" >nul 2>nul
if %errorlevel%==0 (
    python -m motor_control
    goto :eof
)

py -3 -c "import sys" >nul 2>nul
if %errorlevel%==0 (
    py -3 -m motor_control
    goto :eof
)

echo Python 3 was not found.
echo Please install Python 3.11 or later, then run this file again.
pause
