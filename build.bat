@echo off
REM ===================================================================
REM  Builds AFK Farm Clicker into a standalone Windows program.
REM  Put this next to afk_clicker.py and double-click it. Once.
REM  Afterwards you start dist\AFK Farm Clicker\AFK Farm Clicker.exe
REM  and never touch Python or PyCharm again.
REM ===================================================================
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Python was not found. Install it from python.org and tick
    echo   "Add python.exe to PATH" during setup, then run this again.
    echo.
    pause
    exit /b 1
)

echo.
echo === Installing build dependencies ===
py -m pip install --upgrade pip
py -m pip install --upgrade pyinstaller pynput keyboard
if errorlevel 1 (
    echo.
    echo   Dependency install failed -- see the error above.
    pause
    exit /b 1
)

echo.
echo === Building ===
REM --windowed          : it is a Tk app, so no console window behind it
REM --noupx             : UPX compression is a major antivirus red flag
REM --hidden-import ... : pynput and keyboard choose their platform backend at
REM                       import time, so PyInstaller cannot see the Windows
REM                       ones by static analysis and would ship a build that
REM                       dies on launch with ImportError
REM
REM Deliberately NOT --onefile: a single .exe unpacks itself into %TEMP% on
REM every launch, which is slower and is the single biggest trigger for
REM antivirus heuristics. An autoclicker that installs a global keyboard hook
REM is already borderline for most scanners -- do not also hand them a
REM self-extracting stub.
REM
REM If the hotkey does not register while Minecraft has focus, add
REM   --uac-admin
REM to the line below and rebuild. That makes the program ask for
REM administrator rights on every start (UAC prompt), which is only needed
REM when the window you send clicks to is itself running elevated.

py -m PyInstaller --noconfirm --clean ^
    --name "AFK Farm Clicker" ^
    --windowed ^
    --noupx ^
    --hidden-import pynput.mouse._win32 ^
    --hidden-import pynput.keyboard._win32 ^
    --hidden-import keyboard._winkeyboard ^
    afk_clicker.py

if errorlevel 1 (
    echo.
    echo   Build failed -- see the error above.
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo   Done.
echo.
echo   Your program:  dist\AFK Farm Clicker\AFK Farm Clicker.exe
echo.
echo   You can move that whole "AFK Farm Clicker" folder anywhere you
echo   like (Desktop, Startup, ...). Keep the folder together -- the
echo   .exe needs the files beside it.
echo ===================================================================
echo.
pause
