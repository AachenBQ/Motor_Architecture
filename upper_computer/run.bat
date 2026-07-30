@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHON_EXE="
set "ERROR_LOG=%TEMP%\MotorStudio_startup_error.log"

rem Prefer a project virtual environment, then PATH, then common per-user
rem Python installations. This machine currently uses Python 3.6 without a
rem registered "python" or "py -3" command, so the explicit fallback matters.
call :try_python "%~dp0.venv\Scripts\python.exe"

for /f "delims=" %%P in ('where python.exe 2^>nul') do (
    call :try_python "%%~fP"
)

for %%V in (313 312 311 310 39 38 37 36) do (
    call :try_python "%LocalAppData%\Programs\Python\Python%%V\python.exe"
)

if defined PYTHON_EXE goto :run_executable

py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 6))" >nul 2>nul
if not errorlevel 1 goto :run_launcher

echo.
echo Motor Studio could not find Python 3.6 or later.
echo Install Python 3.11 or later, or create:
echo   %~dp0.venv\Scripts\python.exe
echo.
pause
exit /b 1

:run_executable
del /q "%ERROR_LOG%" >nul 2>nul
if /i "%~1"=="--check" (
    "%PYTHON_EXE%" -c "import tkinter; import motor_control.ui; print('Motor Studio startup check: OK')" 2>"%ERROR_LOG%"
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :handle_exit
)
"%PYTHON_EXE%" -m motor_control 2>"%ERROR_LOG%"
set "EXIT_CODE=%ERRORLEVEL%"
goto :handle_exit

:run_launcher
del /q "%ERROR_LOG%" >nul 2>nul
if /i "%~1"=="--check" (
    py -3 -c "import tkinter; import motor_control.ui; print('Motor Studio startup check: OK')" 2>"%ERROR_LOG%"
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :handle_exit
)
py -3 -m motor_control 2>"%ERROR_LOG%"
set "EXIT_CODE=%ERRORLEVEL%"

:handle_exit
if "%EXIT_CODE%"=="0" exit /b 0

echo.
echo Motor Studio failed to start. Exit code: %EXIT_CODE%
if exist "%ERROR_LOG%" (
    echo Error details:
    echo ------------------------------------------------------------
    type "%ERROR_LOG%"
    echo ------------------------------------------------------------
    echo The same details were saved to:
    echo   %ERROR_LOG%
)
echo.
pause
exit /b %EXIT_CODE%

:try_python
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys; raise SystemExit(sys.version_info < (3, 6))" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYTHON_EXE=%~1"
exit /b 0
