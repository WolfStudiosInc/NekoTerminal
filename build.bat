@echo off
title Neko Terminal - Build Executable
echo.
echo  ================================================
echo   Neko Terminal - Build EXE
echo  ================================================
echo.

:: Check for PyInstaller
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PyInstaller...
    pip install pyinstaller
    echo.
)

echo [*] Building Neko Terminal executable...
echo.

python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --icon=neko_icon.ico ^
    --name="NekoTerminal" ^
    --add-data="neko_icon.ico;." ^
    --clean ^
    neko_terminal.py

echo.
if exist "dist\NekoTerminal.exe" (
    echo  ================================================
    echo   BUILD SUCCESSFUL!
    echo   Output: dist\NekoTerminal.exe
    echo  ================================================
    echo.
    echo   - No files are saved to disk when running the exe
    echo   - All data stays in memory only
    echo   - Config resets each launch (by design)
    echo.
) else (
    echo  [ERROR] Build failed. Check output above for details.
)
pause
