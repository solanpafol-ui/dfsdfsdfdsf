@echo off
setlocal
cd /d "%~dp0"
echo.
echo Installing the Chromium build that Playwright needs (~150 MB).
echo Keep this window open until it says Done.
echo.
py -3.12 -m playwright install chromium 2>nul && goto ok
py -m playwright install chromium 2>nul && goto ok
python -m playwright install chromium 2>nul && goto ok
echo.
echo Could not run it automatically. Run this by hand in this folder:
echo    python -m playwright install chromium
pause
exit /b 1
:ok
echo.
dir /b "%LOCALAPPDATA%\ms-playwright\chromium-*" >nul 2>&1 && echo Looks good.
echo Done. Close this window and run run.bat
pause