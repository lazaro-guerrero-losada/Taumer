@echo off
REM One-click PyInstaller Windows Packager for Taumer
echo ========================================================
echo   Taumer — Windows Executable Builder (PyInstaller)
echo ========================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo [1/3] Installing/verifying build requirements...
python -m pip install -r requirements.txt pyinstaller pillow lz4

echo.
echo [2/3] Bundling standalone Windows executable with PyInstaller...
pyinstaller -y taumer.spec

echo.
if exist "dist\Taumer\Taumer.exe" (
    echo [3/3] Packaging Windows ZIP archive...
    copy /Y "app\taumer.ico" "dist\Taumer\" >nul 2>&1
    copy /Y "app\taumer.png" "dist\Taumer\" >nul 2>&1
    echo Taumer — Task ^& Focus Tracker (Windows) > "dist\Taumer\README.txt"
    echo Double-click Taumer.exe to launch! >> "dist\Taumer\README.txt"
    echo. >> "dist\Taumer\README.txt"
    echo NOTE: On Windows, ASCII marine animations are OFF (WebKitGTK is Linux-exclusive). >> "dist\Taumer\README.txt"
    echo All focus timers, stopwatches, task boards, calendar, and Obsidian sync are fully functional. >> "dist\Taumer\README.txt"
    powershell -Command "Compress-Archive -Path 'dist\Taumer' -DestinationPath 'dist\Taumer-Windows-x64.zip' -Force"
    echo.
    echo ========================================================
    echo  SUCCESS! Standalone Windows executable created at:
    echo    dist\Taumer\Taumer.exe
    echo    dist\Taumer-Windows-x64.zip
    echo ========================================================
) else (
    echo.
    echo [ERROR] Build failed. Please check the terminal output above.
)

pause
