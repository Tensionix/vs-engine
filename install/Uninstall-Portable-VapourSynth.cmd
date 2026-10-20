@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Audion VS Engine - Remove Portable VapourSynth

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%A in ("%SCRIPT_DIR%\..") do set "ROOT=%%~fA"

set "NO_PAUSE="
for %%A in (%*) do if /I "%%~A"=="/NOPAUSE" set "NO_PAUSE=1"

set "PS1_FILE=%SCRIPT_DIR%\Uninstall-Portable-VapourSynth.ps1"
set "PS_EXE="

rem The PowerShell the program carries comes first; the one of the machine - where App\ is not built yet.
if exist "%ROOT%\App\AudionPs.exe" set "PS_EXE=%ROOT%\App\AudionPs.exe"
if not defined PS_EXE where pwsh.exe >nul 2>nul && set "PS_EXE=pwsh.exe"
if not defined PS_EXE where powershell.exe >nul 2>nul && set "PS_EXE=powershell.exe"

if not defined PS_EXE goto ERR_NOPS
if not exist "%PS1_FILE%" goto ERR_NOPS1

"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_FILE%" -ProjectRoot "%ROOT%"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto ERR_RUN
echo [DONE] VapourSynth removed.
if not defined NO_PAUSE pause
exit /b 0

:ERR_NOPS
echo [ERROR] No PowerShell found (App\AudionPs.exe, system pwsh, or powershell.exe).
if not defined NO_PAUSE pause
exit /b 1

:ERR_NOPS1
echo [ERROR] PS1 not found: %PS1_FILE%
if not defined NO_PAUSE pause
exit /b 1

:ERR_RUN
echo [ERROR] VapourSynth removal failed (exit %RC%).
if not defined NO_PAUSE pause
exit /b %RC%
