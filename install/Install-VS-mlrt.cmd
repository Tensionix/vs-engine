@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Audion VS Engine - Install vs-mlrt (TensorRT bundle, Phase 18.B-ML)

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%A in ("%SCRIPT_DIR%\..") do set "ROOT=%%~fA"

set "NO_PAUSE="
for %%A in (%*) do if /I "%%~A"=="/NOPAUSE" set "NO_PAUSE=1"

set "PS1_FILE=%SCRIPT_DIR%\Install-VS-mlrt.ps1"
set "PS_EXE="

if exist "%ROOT%\system_core\powershell\pwsh.exe" set "PS_EXE=%ROOT%\system_core\powershell\pwsh.exe"
if not defined PS_EXE where pwsh.exe >nul 2>nul && set "PS_EXE=pwsh.exe"
if not defined PS_EXE where powershell.exe >nul 2>nul && set "PS_EXE=powershell.exe"

if not defined PS_EXE goto ERR_NOPS
if not exist "%PS1_FILE%" goto ERR_NOPS1

rem Flags:
rem   /F or /FORCE     - overwrite existing install
rem   /V <tag>         - pin specific vs-mlrt version (default: latest)
rem   /NO-MODELS       - skip the ~852 MB models pack (CI / headless usage)
rem   /LEAN            - trim builder resources to local SM + drop unused models
rem   /DROP-CACHE      - optional: central install cache cleanup after success
rem   /FULL            - explicit FULL bundle (negates /LEAN,
rem                      useful for offline distribution images)
rem   /NOPAUSE         - non-interactive mode for GUI / automation callers
set "OPT_FORCE="
set "OPT_VERSION="
set "OPT_NOMODELS="
set "OPT_LEAN=-Lean"
set "OPT_DROPCACHE="
:PARSE
if "%~1"=="" goto SHOW
if /I "%~1"=="/F"          ( set "OPT_FORCE=-Force" & shift & goto PARSE )
if /I "%~1"=="/FORCE"      ( set "OPT_FORCE=-Force" & shift & goto PARSE )
if /I "%~1"=="/V"          ( set "OPT_VERSION=-MLRTVersion %~2" & shift & shift & goto PARSE )
if /I "%~1"=="/NO-MODELS"  ( set "OPT_NOMODELS=-NoModels" & shift & goto PARSE )
if /I "%~1"=="/NOMODELS"   ( set "OPT_NOMODELS=-NoModels" & shift & goto PARSE )
if /I "%~1"=="/LEAN"       ( set "OPT_LEAN=-Lean" & shift & goto PARSE )
if /I "%~1"=="/DROP-CACHE" ( set "OPT_DROPCACHE=-DropCache" & shift & goto PARSE )
if /I "%~1"=="/DROPCACHE"  ( set "OPT_DROPCACHE=-DropCache" & shift & goto PARSE )
if /I "%~1"=="/FULL"       ( set "OPT_LEAN=" & set "OPT_DROPCACHE=" & shift & goto PARSE )
if /I "%~1"=="/NOPAUSE"    ( set "NO_PAUSE=1" & shift & goto PARSE )
shift
goto PARSE

:SHOW
echo ======================================================================
echo   AUDION VS ENGINE - INSTALL VS-MLRT (CMD wrapper)
echo ======================================================================
echo PS engine:  %PS_EXE%
echo Project:    %ROOT%
call :PRINT_MODE
if defined OPT_FORCE    echo Force:      %OPT_FORCE%
if defined OPT_VERSION  echo Pinned:     %OPT_VERSION%
if defined OPT_NOMODELS echo Models:     SKIPPED (--no-models)
if not defined OPT_NOMODELS echo Models:     YES (downloads ~852 MB models pack)
if defined NO_PAUSE    echo Noninteractive: ON
echo.
echo This is a slow step. Coffee-grade wait expected on a slow connection.
echo.

"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_FILE%" -ProjectRoot "%ROOT%" %OPT_FORCE% %OPT_VERSION% %OPT_NOMODELS% %OPT_LEAN% %OPT_DROPCACHE%
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" goto ERR_RUN
echo [DONE] vs-mlrt install completed.
if not defined NO_PAUSE pause
exit /b 0

:PRINT_MODE
if defined OPT_LEAN if defined OPT_DROPCACHE goto MODE_LEAN_DROPCACHE
if defined OPT_LEAN goto MODE_LEAN
if defined OPT_DROPCACHE goto MODE_DROPCACHE
goto MODE_FULL

:MODE_LEAN_DROPCACHE
echo Mode:       LEAN ^+ DROP-CACHE  -^> trims local GPU set, then clears install cache
goto :eof

:MODE_LEAN
echo Mode:       LEAN  ^[default^]  -^> trims to local GPU SM ^(keeps install cache^)
goto :eof

:MODE_DROPCACHE
echo Mode:       DROP-CACHE  -^> full bundle without cache
goto :eof

:MODE_FULL
echo Mode:       FULL bundle  -^> ~10 GB ^(for offline distribution^)
goto :eof

:ERR_NOPS
echo [ERROR] No PowerShell found (portable, system pwsh, or powershell.exe).
if not defined NO_PAUSE pause
exit /b 1

:ERR_NOPS1
echo [ERROR] PS1 not found: %PS1_FILE%
if not defined NO_PAUSE pause
exit /b 1

:ERR_RUN
echo [ERROR] vs-mlrt install failed (exit %RC%).
if not defined NO_PAUSE pause
exit /b %RC%
