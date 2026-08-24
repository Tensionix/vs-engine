@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

title Audion VS Engine - Film Looks (Русский)

for %%I in ("%~dp0..") do set "BASE_DIR=%%~fI"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"
cd /d "%BASE_DIR%"

set "CORE_DIR=%BASE_DIR%\system_core"
set "RUNTIME_DIR=%BASE_DIR%\._runtime"
set "MENU_FILE=%RUNTIME_DIR%\film_looks_menu_ru.txt"
set "RES_FILE=%RUNTIME_DIR%\film_looks_menu_ru_res.txt"

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%" >nul 2>nul

call :RESOLVE_PYTHON
if errorlevel 1 goto NO_PYTHON

call :RESOLVE_FZF
if errorlevel 1 (
  set "MENU_MODE=CMD fallback"
) else (
  set "MENU_MODE=FZF"
)

:MAIN
cls
echo ======================================================================
echo   AUDION VS ENGINE - FILM LOOKS  (киноплёнка)
echo ======================================================================
echo Корень:    %BASE_DIR%
echo Python:    %PYTHON_CMD% %PYTHON_ARGS%
echo Меню:      %MENU_MODE%
echo Подсказка: intensity 0.0 = выкл, 1.0 = настроено, 2.0 = сильно
echo.

if defined FZF_CMD goto FZF_MENU
goto FALLBACK_MENU

:FZF_MENU
> "%MENU_FILE%" echo === Плёночные луки (от мягких к экстремальным) ====================
>>"%MENU_FILE%" echo [01] Cinematic             ^| cinematic       ^| универсальный лёгкий filmic, безопасный default
>>"%MENU_FILE%" echo [02] Film 35mm             ^| film_35mm       ^| Kodak (варианты: 250D / 500T / 50D)
>>"%MENU_FILE%" echo [03] Film 16mm             ^| film_16mm       ^| органичный, более зернистый, поднятые тени
>>"%MENU_FILE%" echo [04] Super 8               ^| super8          ^| самое сильное зерно, мягкая оптика, выцветшие 70-е
>>"%MENU_FILE%" echo [05] Bleach Bypass         ^| bleach_bypass   ^| высокий контраст, десатурация, жёстко
>>"%MENU_FILE%" echo [06] IMAX 70mm             ^| imax_70mm       ^| large format -- минимум зерна, лёгкая halation, 1px gate weave
>>"%MENU_FILE%" echo [07] Anamorphic scope      ^| anamorphic      ^| Hollywood cinemascope -- горизонтальные blue lens flares + teal shadows
>>"%MENU_FILE%" echo.
>>"%MENU_FILE%" echo === Сервис ========================================================
>>"%MENU_FILE%" echo [08] Список энкодеров      ^| list_encoders   ^| H.264 / H.265 / ProRes / DNxHR
>>"%MENU_FILE%" echo [09] Доктор                ^| doctor          ^| диагностика стека
>>"%MENU_FILE%" echo [10] Открыть папку input   ^| open_input      ^| Explorer
>>"%MENU_FILE%" echo [11] Открыть папку output  ^| open_output     ^| Explorer
>>"%MENU_FILE%" echo [12] Открыть папку logs    ^| open_logs       ^| JSON отчёты
>>"%MENU_FILE%" echo [00] Назад / Выход         ^| exit            ^| закрыть

"%FZF_CMD%" --prompt="audion@film-looks-ru > " --pointer=">" --header="От лёгкого (cinematic) до экстремального (super8). Выберите лук." --layout=reverse --border=rounded --info=hidden --margin=1,2 < "%MENU_FILE%" > "%RES_FILE%"

set "CHOICE="
set /p CHOICE=<"%RES_FILE%"
if not defined CHOICE goto MAIN

for /f "tokens=2 delims=|" %%a in ("%CHOICE%") do set "RAW=%%a"
call :TRIM RAW

if /I "%RAW%"=="cinematic"     goto CINEMATIC
if /I "%RAW%"=="film_35mm"     goto FILM_35MM
if /I "%RAW%"=="film_16mm"     goto FILM_16MM
if /I "%RAW%"=="super8"        goto SUPER8
if /I "%RAW%"=="bleach_bypass" goto BLEACH_BYPASS
if /I "%RAW%"=="imax_70mm"     goto IMAX_70MM
if /I "%RAW%"=="anamorphic"    goto ANAMORPHIC
if /I "%RAW%"=="list_encoders" goto LIST_ENCODERS
if /I "%RAW%"=="doctor"        goto DOCTOR
if /I "%RAW%"=="open_input"    goto OPEN_INPUT
if /I "%RAW%"=="open_output"   goto OPEN_OUTPUT
if /I "%RAW%"=="open_logs"     goto OPEN_LOGS
if /I "%RAW%"=="exit"          exit /b 0
goto MAIN

:FALLBACK_MENU
echo === Плёночные луки ===
echo [1] Cinematic           (универсальный, безопасный)
echo [2] Film 35mm           (Kodak 250D / 500T / 50D)
echo [3] Film 16mm           (органика, больше зерна)
echo [4] Super 8             (выцветшие 70-е)
echo [5] Bleach Bypass       (высокий контраст, десатур.)
echo [6] IMAX 70mm           (large format, минимум зерна, gate weave)
echo [7] Anamorphic scope    (cinemascope blue flares + teal shadows)
echo.
echo === Сервис ===
echo [8] Список энкодеров
echo [9] Доктор
echo [A] Открыть папку input
echo [B] Открыть папку output
echo [C] Открыть папку logs
echo [0] Назад / Выход
echo.
choice /C 123456789ABC0 /N /M "Выбор: "
if errorlevel 13 exit /b 0
if errorlevel 12 goto OPEN_LOGS
if errorlevel 11 goto OPEN_OUTPUT
if errorlevel 10 goto OPEN_INPUT
if errorlevel 9  goto DOCTOR
if errorlevel 8  goto LIST_ENCODERS
if errorlevel 7  goto ANAMORPHIC
if errorlevel 6  goto IMAX_70MM
if errorlevel 5  goto BLEACH_BYPASS
if errorlevel 4  goto SUPER8
if errorlevel 3  goto FILM_16MM
if errorlevel 2  goto FILM_35MM
if errorlevel 1  goto CINEMATIC
goto MAIN


REM =====================================================================
REM Действия пресетов
REM =====================================================================

:CINEMATIC
call :ASK_INPUT_FILE
call :ASK_OUTPUT_FILE cinematic
call :ASK_INTENSITY
call :ASK_ENCODER
call :RUN_PRESET cinematic --intensity %INTENSITY%
goto MAIN

:FILM_35MM
call :ASK_INPUT_FILE
call :ASK_OUTPUT_FILE film_35mm
call :ASK_STOCK
call :ASK_INTENSITY
call :ASK_ENCODER
call :RUN_PRESET film_35mm --stock %STOCK% --intensity %INTENSITY%
goto MAIN

:FILM_16MM
call :ASK_INPUT_FILE
call :ASK_OUTPUT_FILE film_16mm
call :ASK_INTENSITY
call :ASK_ENCODER
call :RUN_PRESET film_16mm --intensity %INTENSITY%
goto MAIN

:SUPER8
call :ASK_INPUT_FILE
call :ASK_OUTPUT_FILE super8
call :ASK_INTENSITY
call :ASK_ENCODER
call :RUN_PRESET super8 --intensity %INTENSITY%
goto MAIN

:BLEACH_BYPASS
call :ASK_INPUT_FILE
call :ASK_OUTPUT_FILE bleach_bypass
call :ASK_INTENSITY
call :ASK_ENCODER
call :RUN_PRESET bleach_bypass --intensity %INTENSITY%
goto MAIN

:IMAX_70MM
call :ASK_INPUT_FILE
call :ASK_OUTPUT_FILE imax_70mm
call :ASK_INTENSITY
call :ASK_GATE_WEAVE
call :ASK_ENCODER
call :RUN_PRESET imax_70mm --intensity %INTENSITY% --gate-weave %GATE_WEAVE%
goto MAIN

:ANAMORPHIC
call :ASK_INPUT_FILE
call :ASK_OUTPUT_FILE anamorphic
call :ASK_INTENSITY
call :ASK_FLARE_LEN
call :ASK_FLARE_THR
call :ASK_TEAL_SHADOW
call :ASK_ENCODER
call :RUN_PRESET anamorphic_scope --intensity %INTENSITY% --flare-len %FLARE_LEN% --flare-thr %FLARE_THR% --teal-shadow %TEAL_SHADOW%
goto MAIN

:LIST_ENCODERS
call :RUNPY "%CORE_DIR%\main.py" list-encoders
if not defined AUDION_NO_PAUSE pause
goto MAIN

:DOCTOR
call :RUNPY "%CORE_DIR%\doctor.py"
if not defined AUDION_NO_PAUSE pause
goto MAIN

:OPEN_INPUT
start "" explorer "%BASE_DIR%\input"
goto MAIN

:OPEN_OUTPUT
start "" explorer "%BASE_DIR%\output"
goto MAIN

:OPEN_LOGS
start "" explorer "%BASE_DIR%\logs"
goto MAIN


REM =====================================================================
REM Параметры (UI prompts)
REM =====================================================================

:ASK_INPUT_FILE
set "SRC_PATH="
echo.
echo [INFO] Нажмите Enter для папки input проекта или укажите путь к файлу/папке.
set /p SRC_PATH=Файл или папка input [input] :
if not defined SRC_PATH set "SRC_PATH=%BASE_DIR%\input"
goto :eof

:ASK_OUTPUT_FILE
set "DST_PATH="
echo.
set /p DST_PATH=Выходной файл [output\out_%~1.mp4] :
if not defined DST_PATH set "DST_PATH=%BASE_DIR%\output\out_%~1.mp4"
goto :eof

:ASK_INTENSITY
set "INTENSITY="
echo.
echo Сила воздействия (масштабирует зерно, halation, мягкость оптики):
echo   1 - 0.5  (едва заметно / безопасно)
echo   2 - 1.0  (настроенный default)
echo   3 - 1.5  (заметно)
echo   4 - 2.0  (сильно)
set /p INTENSITY=Выбор или число [2] :
if not defined INTENSITY set "INTENSITY=1.0"
if /I "%INTENSITY%"=="1" set "INTENSITY=0.5"
if /I "%INTENSITY%"=="2" set "INTENSITY=1.0"
if /I "%INTENSITY%"=="3" set "INTENSITY=1.5"
if /I "%INTENSITY%"=="4" set "INTENSITY=2.0"
goto :eof

:ASK_STOCK
set "STOCK="
echo.
echo Вариант плёнки Kodak 35mm:
echo   1 - 250D   (дневной, нейтральный, тонкое зерно) -- по умолчанию
echo   2 - 500T   (вольфрамовый, быстрее, прохладнее)
echo   3 - 50D    (дневной, чистейшее зерно)
set /p STOCK=Выбор [1] :
if not defined STOCK set "STOCK=250D"
if /I "%STOCK%"=="1" set "STOCK=250D"
if /I "%STOCK%"=="2" set "STOCK=500T"
if /I "%STOCK%"=="3" set "STOCK=50D"
goto :eof

:ASK_GATE_WEAVE
set "GATE_WEAVE="
echo.
echo Gate weave (1px случайное смещение кадра, имитирует плёнку в gate):
echo   1 - вкл  (по умолчанию; даёт лёгкое "живое" ощущение плёнки)
echo   2 - выкл (стабильные цифровые кадры)
set /p GATE_WEAVE=Выбор [1] :
if not defined GATE_WEAVE set "GATE_WEAVE=1"
if /I "%GATE_WEAVE%"=="1" set "GATE_WEAVE=1"
if /I "%GATE_WEAVE%"=="2" set "GATE_WEAVE=0"
goto :eof

:ASK_FLARE_LEN
set "FLARE_LEN="
echo.
echo Длина anamorphic streak (в пикселях):
echo   1 - 48    (тонко)
echo   2 - 96    (по умолчанию; классический Panavision)
echo   3 - 160   (драматично; Abrams-style)
echo   4 - 256   (экстрим; явный "Star Trek lens flare")
set /p FLARE_LEN=Выбор [2] :
if not defined FLARE_LEN set "FLARE_LEN=96"
if /I "%FLARE_LEN%"=="1" set "FLARE_LEN=48"
if /I "%FLARE_LEN%"=="2" set "FLARE_LEN=96"
if /I "%FLARE_LEN%"=="3" set "FLARE_LEN=160"
if /I "%FLARE_LEN%"=="4" set "FLARE_LEN=256"
goto :eof

:ASK_FLARE_THR
set "FLARE_THR="
echo.
echo Порог highlight для срабатывания flare (ниже = больше пикселей дают вспышку):
echo   1 - 0.85   (только самые яркие highlights)
echo   2 - 0.78   (по умолчанию; яркие источники света и specular)
echo   3 - 0.70   (агрессивнее; яркая кожа / небо тоже)
echo   4 - 0.60   (тяжело; midtones тоже участвуют)
set /p FLARE_THR=Выбор [2] :
if not defined FLARE_THR set "FLARE_THR=0.78"
if /I "%FLARE_THR%"=="1" set "FLARE_THR=0.85"
if /I "%FLARE_THR%"=="2" set "FLARE_THR=0.78"
if /I "%FLARE_THR%"=="3" set "FLARE_THR=0.70"
if /I "%FLARE_THR%"=="4" set "FLARE_THR=0.60"
goto :eof

:ASK_TEAL_SHADOW
set "TEAL_SHADOW="
echo.
echo Teal-cool тень (J.J.Abrams / Nolan эстетика):
echo   1 - 0.0    (выкл; тёплые или нейтральные тени)
echo   2 - 0.20   (тонко; еле заметный намёк)
echo   3 - 0.35   (по умолчанию; классический blockbuster)
echo   4 - 0.60   (тяжёлый; явно стилизовано)
set /p TEAL_SHADOW=Выбор [3] :
if not defined TEAL_SHADOW set "TEAL_SHADOW=0.35"
if /I "%TEAL_SHADOW%"=="1" set "TEAL_SHADOW=0.0"
if /I "%TEAL_SHADOW%"=="2" set "TEAL_SHADOW=0.20"
if /I "%TEAL_SHADOW%"=="3" set "TEAL_SHADOW=0.35"
if /I "%TEAL_SHADOW%"=="4" set "TEAL_SHADOW=0.60"
goto :eof

:ASK_ENCODER
set "ENCODER="
echo.
echo Профиль энкодера:
echo   1 - h264_crf14       (по умолчанию; semi-lossless, архивное качество)
echo   2 - h264_crf17       (почти невидимый lossy, Audion tier)
echo   3 - h264_crf21       (web / proxy / превью)
echo   4 - h265_crf17       (HEVC, меньше размер при том же качестве)
echo   5 - prores_lt        (ProRes по умолчанию; для DaVinci / round-trip)
echo   6 - prores_lt_mxf    (ProRes LT в MXF wrapper для Adobe / Avid)
echo   7 - h264_nvenc_q14   (NVIDIA hardware encode; разгружает CPU)
echo   8 - h265_nvenc_q17   (NVIDIA hardware HEVC; 10-bit p010le)
set /p ENCODER=Выбор [1] :
if not defined ENCODER set "ENCODER=h264_crf14"
if /I "%ENCODER%"=="1" set "ENCODER=h264_crf14"
if /I "%ENCODER%"=="2" set "ENCODER=h264_crf17"
if /I "%ENCODER%"=="3" set "ENCODER=h264_crf21"
if /I "%ENCODER%"=="4" set "ENCODER=h265_crf17"
if /I "%ENCODER%"=="5" set "ENCODER=prores_lt"
if /I "%ENCODER%"=="6" set "ENCODER=prores_lt_mxf"
if /I "%ENCODER%"=="7" set "ENCODER=h264_nvenc_q14"
if /I "%ENCODER%"=="8" set "ENCODER=h265_nvenc_q17"
goto :eof


REM =====================================================================
REM Запуск пресета
REM =====================================================================

:RUN_PRESET
set "PRESET=%~1"
shift
set "EXTRA="
:RUN_PRESET_LOOP
if "%~1"=="" goto RUN_PRESET_GO
set "EXTRA=%EXTRA% %~1"
shift
goto RUN_PRESET_LOOP
:RUN_PRESET_GO
echo.
echo [запуск] film_looks/%PRESET%
echo          вход:    %SRC_PATH%
echo          выход:   %DST_PATH%
echo          энкодер: %ENCODER%
echo.
call :RUNPY "%CORE_DIR%\main.py" run --palette film_looks --preset %PRESET% --input "%SRC_PATH%" --output "%DST_PATH%" --encoder %ENCODER%%EXTRA%
echo.
if not defined AUDION_NO_PAUSE pause
goto :eof


REM =====================================================================
REM Plumbing
REM =====================================================================

:NO_PYTHON
cls
echo [ОШИБКА] Python оркестратора не найден.
echo Ожидается: runtime\python.exe
echo Запустите builder_main.cmd -^> [01] BUILD PORTABLE ENV
if not defined AUDION_NO_PAUSE pause
exit /b 1

:RUNPY
set "TARGET=%~1"
if not exist "%TARGET%" (
  echo [ОШИБКА] Скрипт не найден:
  echo %TARGET%
  goto :eof
)
"%PYTHON_CMD%" %PYTHON_ARGS% %*
goto :eof

:RESOLVE_PYTHON
set "PYTHON_CMD="
set "PYTHON_ARGS="
if exist "%BASE_DIR%\runtime\python.exe" (
  set "PYTHON_CMD=%BASE_DIR%\runtime\python.exe"
  goto PY_OK
)
if exist "%BASE_DIR%\runtime\python\python.exe" (
  set "PYTHON_CMD=%BASE_DIR%\runtime\python\python.exe"
  goto PY_OK
)
py -3.12 -V >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=py"
  set "PYTHON_ARGS=-3.12"
  goto PY_OK
)
where python >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  goto PY_OK
)
exit /b 1
:PY_OK
exit /b 0

:RESOLVE_FZF
set "FZF_CMD="
if /I "%AUDION_DISABLE_FZF%"=="1" exit /b 1
if exist "%CORE_DIR%\fzf.exe" (
  set "FZF_CMD=%CORE_DIR%\fzf.exe"
  exit /b 0
)
where fzf >nul 2>nul
if not errorlevel 1 (
  set "FZF_CMD=fzf"
  exit /b 0
)
exit /b 1

:TRIM
for /f "tokens=* delims= " %%z in ("!%~1!") do set "%~1=%%z"
:TRIM_R
if "!%~1:~-1!"==" " set "%~1=!%~1:~0,-1!" & goto TRIM_R
goto :eof
