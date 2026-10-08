@echo off
echo ==========================================
echo Building DarkAgent Pro Launcher...
echo ==========================================

:: Usa o venv do projeto (precisa ter torch CPU + requirements instalados)
call venv\Scripts\activate.bat || goto :fail
pip install --quiet pyinstaller || goto :fail

:: Checagem estrutural antes de gastar ~10 min de build
python scripts\check_structure.py || goto :fail

:: NUNCA apagar DarkAgentLauncher.spec — ele e a fonte de verdade do build
:: (pathex, collect_submodules, yt_dlp, etc.). --clean ja limpa build/ e cache.
if exist "dist\DarkAgentLauncher.exe" del /q "dist\DarkAgentLauncher.exe"
pyinstaller DarkAgentLauncher.spec --clean --noconfirm || goto :fail

if not exist "dist\DarkAgentLauncher.exe" goto :fail

echo ==========================================
echo Build Successful!
echo Executable located at: dist\DarkAgentLauncher.exe
echo ==========================================
pause
exit /b 0

:fail
echo ==========================================
echo Build Failed!
echo ==========================================
pause
exit /b 1
