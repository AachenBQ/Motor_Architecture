@echo off
setlocal
cd /d "%~dp0"
python -m motor_control.codex_client %*
