@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo === MotionDeck build ===

if not exist ".venv\Scripts\python.exe" (
    echo [!] .venv not found. Run:
    echo     python -m venv .venv
    echo     .venv\Scripts\activate
    echo     pip install -r requirements.txt
    exit /b 1
)

echo [1/6] Checking package data...
if not exist "motiondeck\bypass_ext\manifest.json" (
    echo [!] motiondeck\bypass_ext\manifest.json is missing.
    echo     The build would ship without the shield extension.
    exit /b 1
)
if not exist "motiondeck\skills" (
    echo [!] motiondeck\skills is missing. Skill prompts would not ship.
    exit /b 1
)

echo [2/6] Installing build dependency...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 exit /b 1

echo [3/6] Ensuring the bundled Chromium is installed...
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 exit /b 1

echo [4/6] Building...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean build.spec
if errorlevel 1 (
    echo [!] Build failed.
    exit /b 1
)

echo [5/6] Verifying the frozen tree...
if not exist "dist\MotionDeck\MotionDeck.exe" (
    echo [!] No exe produced.
    exit /b 1
)
if not exist "dist\MotionDeck\_internal\motiondeck\bypass_ext\manifest.json" (
    echo [!] bypass_ext did not make it into the bundle.
    echo     The app would run without the shield extension.
    exit /b 1
)
if not exist "dist\MotionDeck\_internal\motiondeck\skills" (
    echo [!] skills did not make it into the bundle.
    exit /b 1
)

echo [6/6] Copying docs...
copy /y "FIRST_RUN.md" "dist\MotionDeck\FIRST_RUN.md" >nul 2>&1

echo.
echo === Done: dist\MotionDeck\MotionDeck.exe ===
echo Zip the whole dist\MotionDeck folder; the exe alone will not run.
endlocal