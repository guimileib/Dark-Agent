@echo off
echo ==========================================
echo Building DarkAgent Pro Launcher...
echo ==========================================

:: Ensure PyInstaller is installed
pip install pyinstaller

:: Clean previous builds
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "DarkAgentLauncher.spec" del "DarkAgentLauncher.spec"

:: Run PyInstaller
:: --noconsole: Hide terminal window
:: --onefile: Create a single executable
:: --name: Name of the output file
:: --icon: Application icon
:: --add-data: Include assets folder
:: --collect-all: Ensure complex packages are fully included
pyinstaller ^
    --noconsole ^
    --onefile ^
    --name "DarkAgentLauncher" ^
    --icon "src/assets/icon.png" ^
    --add-data "src/assets;src/assets" ^
    --add-data "src/config;src/config" ^
    --collect-all "whisper" ^
    --collect-all "torch" ^
    --hidden-import "PIL" ^
    --hidden-import "PyQt6" ^
    src/launcher.py

echo ==========================================
if exist "dist\DarkAgentLauncher.exe" (
    echo Build Successful!
    echo Executable located at: dist\DarkAgentLauncher.exe
) else (
    echo Build Failed!
)
echo ==========================================
pause
