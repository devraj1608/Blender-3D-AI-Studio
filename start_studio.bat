@echo off
REM Start Blender Image-to-3D Web Studio on Windows
title Blender Image-to-3D Studio

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo ❌ Error: Virtual environment .venv not found.
    echo Please create one with: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

set PORT=8000

echo ==========================================================
echo 🚀 Blender Image-to-3D Studio (Windows)
echo ==========================================================
echo • Web Studio UI:  http://127.0.0.1:%PORT%
echo • Blender Bridge: 127.0.0.1:9876
echo ==========================================================
echo Opening Web Studio in your browser...

start http://127.0.0.1:%PORT%
python web_app.py
pause
