@echo off
REM Launcher for Taumer on Windows
set "SCRIPT_DIR=%~dp0"
set "PYTHONPATH=%SCRIPT_DIR%app;%PYTHONPATH%"
python "%SCRIPT_DIR%app\main.py" %*
