@echo off
rem Open MotionDeck Studio with a Python that actually has Tkinter.
rem The bundled WorkBuddy python has no tkinter, so prefer the system 3.12.
setlocal
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=py"
if /i "%PY%"=="py" (
  start "" py -3 "%~dp0main.py"
) else (
  start "" "%PY%" "%~dp0main.py"
)
