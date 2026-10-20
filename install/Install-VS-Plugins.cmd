@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Audion VS Engine - Install VS Plugins

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%A in ("%SCRIPT_DIR%\..") do set "ROOT=%%~fA"

set "NO_PAUSE="
for %%A in (%*) do if /I "%%~A"=="/NOPAUSE" set "NO_PAUSE=1"

set "PS1_FILE=%SCRIPT_DIR%\Install-VS-Plugins.ps1"
set "PS_EXE="

rem The PowerShell the program carries comes first; the one of the machine - where App\ is not built yet.
if exist "%ROOT%\App\AudionPs.exe" set "PS_EXE=%ROOT%\App\AudionPs.exe"
if not defined PS_EXE where pwsh.exe >nul 2>nul && set "PS_EXE=pwsh.exe"
if not defined PS_EXE where powershell.exe >nul 2>nul && set "PS_EXE=powershell.exe"

if not defined PS_EXE goto ERR_NOPS
if not exist "%PS1_FILE%" goto ERR_NOPS1

rem   /NOPAUSE         - non-interactive mode for GUI / automation callers
rem BM3D on the GPU of any vendor goes through Vulkan (bm3dvk), so there is no CUDA switch.

echo ======================================================================
echo   AUDION VS ENGINE - INSTALL VS PLUGINS (CMD wrapper)
echo ======================================================================
echo PS engine: %PS_EXE%
echo Project:   %ROOT%
if defined NO_PAUSE        echo Noninteractive: ON
echo.

"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_FILE%" -ProjectRoot "%ROOT%"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [DONE] All plugins installed.
  if not defined NO_PAUSE pause
  exit /b 0
)
if "%RC%"=="2" (
  echo [PARTIAL] Some plugins failed - see summary above.
  if not defined NO_PAUSE pause
  exit /b 2
)
echo [ERROR] Plugin install failed (exit %RC%).
if not defined NO_PAUSE pause
exit /b %RC%

:ERR_NOPS
echo [ERROR] No PowerShell found.
if not defined NO_PAUSE pause
exit /b 1

:ERR_NOPS1
echo [ERROR] PS1 not found: %PS1_FILE%
if not defined NO_PAUSE pause
exit /b 1
