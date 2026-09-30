@echo off
REM Universal Windows Launcher for Blender Image-to-3D Bridge
title Launch Blender Image-to-3D Bridge

set "SCRIPT_DIR=%~dp0"
set "BRIDGE_SCRIPT=%SCRIPT_DIR%blender_addon\mcp_bridge.py"
set "BLENDER_BIN="

echo ==========================================================
echo 🎨 Blender Image-to-3D Bridge Launcher (Windows)
echo ==========================================================

REM 1. Check Blender in PATH
where blender.exe >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "BLENDER_BIN=blender.exe"
    goto :FOUND
)

REM 2. Search common 64-bit Program Files installation paths
for /d %%D in ("C:\Program Files\Blender Foundation\Blender *") do (
    if exist "%%D\blender.exe" (
        set "BLENDER_BIN=%%D\blender.exe"
    )
)
if defined BLENDER_BIN goto :FOUND

REM 3. Search Local AppData installation paths
for /d %%D in ("%LOCALAPPDATA%\Programs\Blender Foundation\Blender *") do (
    if exist "%%D\blender.exe" (
        set "BLENDER_BIN=%%D\blender.exe"
    )
)
if defined BLENDER_BIN goto :FOUND

REM 4. Search Steam Blender installation
if exist "C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe" (
    set "BLENDER_BIN=C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
    goto :FOUND
)

echo ❌ Error: Could not locate blender.exe automatically.
echo Please install Blender from https://www.blender.org/download/
echo Or run Blender manually, open Blender's 'Scripting' tab,
echo open "%BRIDGE_SCRIPT%" and click 'Run Script' (Play button).
pause
exit /b 1

:FOUND
echo 🚀 Found Blender at: "%BLENDER_BIN%"
echo 🔌 Starting Blender with bridge on 127.0.0.1:9876...
start "" "%BLENDER_BIN%" --python "%BRIDGE_SCRIPT%"
echo ✅ Blender launched! Listening on port 9876.
