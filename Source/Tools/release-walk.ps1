# The built program walked through without a mouse: its own buttons are pressed by UI Automation.
#
#   Source\Tools\release-walk.ps1 -Stand C:\Temp\vs_stand
#
# A release build has no steps of a check inside, so the stand is a copy of the program: App\, the
# console command, the engine - system_core with VapourSynth and its plugins, and the list of the set,
# install\vs_plugins.json - the Python of the project, FFmpeg and FFprobe of Tools\ffmpeg\bin and
# config\ without the files of the owner (the history of paths, the forms and the look of the window).
# Its input, output, logs and report are its own - nothing of the owner's is read or written. The
# window is started with AUDION_WALK=1: it and its questions stand off every screen and take no focus.
# It is found by the id of its process, never by its name or title; the pointer is not moved.
#
# What is pressed: a palette and a preset of its groups, a choice of the cards of the encoder (MKV), the
# slider of a number, the preview under the form (the middle frame before and after, the next video of
# the Source), COMMAND (the commands said, nothing written), RUN of the preset, LIST and DETAILS of the
# work zone, SAVE AS PROFILE with its question and a run of the profile on PROFILES, the pin of the
# Source, TO SOURCE with its question, CLEAR with its menu and its question (the files of the stand go
# to the Recycle Bin), RUN on an empty Source (refused before it began), STOP while BM3D on the
# processor goes over a minute of 1080p (no half-written file is left), and the window closed while
# one goes. SETUP of the header: its sheet with the components. Then the window once more with an NVIDIA
# RTX card named to it (AUDION_VS_RTX): the question of the additional components comes at the start with
# MLRT in it - INSTALL LATER says where SETUP is - the neural presets are in RESTORATION, their page shows
# the installation of MLRT, SETUP offers it. And once more with the engine of the stand put aside: the
# question names VapourSynth and its plugins, SETUP offers INSTALL ALL - nothing is installed. Exit code 0 -
# every check held; 1 - one did not, and the line says which.
#
# Needs a PowerShell with the WindowsDesktop assemblies (an installed PowerShell 7).
# -Keep leaves the stand in place for a look; otherwise it is removed at the end.
param(
    [Parameter(Mandatory)][string]$Stand,
    # The built window to walk: App\ of the program, or another build of it.
    [string]$App = '',
    [switch]$Keep
)
$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
$project = Split-Path -Parent $source
$window = 'AudionVSEngine.exe'
if (-not $App) { $App = Join-Path $project 'App' }

if (Test-Path -LiteralPath $Stand) { "the stand must not exist yet: $Stand"; exit 2 }
if (-not (Test-Path -LiteralPath (Join-Path $App $window))) { "no built window in $App`: install\Build-App.cmd"; exit 2 }
if (-not (Test-Path -LiteralPath (Join-Path $project 'system_core\vapoursynth'))) { "no engine in the program: SERVICE -> Install VapourSynth"; exit 2 }
[void](New-Item -ItemType Directory -Force -Path $Stand)
$Stand = (Resolve-Path -LiteralPath $Stand).Path
$copies = @(
    @($App, 'App', @(), @()),
    @((Join-Path $project 'system_core'), 'system_core', @('__pycache__', 'powershell'), @()),
    @((Join-Path $project 'runtime'), 'runtime', @('__pycache__'), @()),
    @((Join-Path $project 'config'), 'config', @(), @('window_settings.json*', 'path_history.json*')),
    @((Join-Path $project 'Tools\ffmpeg\bin'), 'Tools\ffmpeg\bin', @(), @('ffplay.exe'))
)
foreach ($copy in $copies) {
    $skip = @()
    if ($copy[2].Count -gt 0) { $skip += @('/XD') + $copy[2] }
    if ($copy[3].Count -gt 0) { $skip += @('/XF') + $copy[3] }
    $null = robocopy $copy[0] (Join-Path $Stand $copy[1]) /E @skip /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) { "the copy of $($copy[1]) failed"; exit 2 }
}
Copy-Item -LiteralPath (Join-Path $project 'vs_cli.cmd') -Destination $Stand
[void](New-Item -ItemType Directory -Force -Path (Join-Path $Stand 'install'))
Copy-Item -LiteralPath (Join-Path $project 'install\vs_plugins.json') -Destination (Join-Path $Stand 'install')
$in = Join-Path $Stand 'input'; $out = Join-Path $Stand 'output'
foreach ($name in 'input', 'output', 'logs', 'report') { [void](New-Item -ItemType Directory -Force -Path (Join-Path $Stand $name)) }
$exe = Join-Path $Stand "App\$window"
$ffmpeg = Join-Path $Stand 'Tools\ffmpeg\bin\ffmpeg.exe'
# The profile the walk saves is its own: one of that name the copy brought is not the walk's.
$profile = Join-Path $Stand 'config\profiles\deband_safe_mine.json'
if (Test-Path -LiteralPath $profile) { Remove-Item -LiteralPath $profile }

# Clips of the stand, made by its own FFmpeg: a test picture with a tone under it.
function MakeClip([string]$name, [int]$seconds, [string]$size) {
    & $ffmpeg -hide_banner -loglevel error -f lavfi -i "testsrc2=size=$size`:rate=25:duration=$seconds" -f lavfi -i "sine=frequency=440:duration=$seconds" `
        -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -shortest (Join-Path $in $name)
    if ($LASTEXITCODE -ne 0) { throw "the clip $name of the stand was not made" }
}
function FilesIn([string]$folder) { @(Get-ChildItem -LiteralPath $folder -Recurse -File -Force -ErrorAction SilentlyContinue) }

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$auto = [System.Windows.Automation.AutomationElement]
$failed = 0
function Say([bool]$ok, [string]$what) {
    '{0} {1}' -f $(if ($ok) { '[OK]  ' } else { '[FAIL]' }), $what
    if (-not $ok) { $script:failed++ }
}
function Find($root, [string]$id, [int]$seconds = 20) {
    $condition = [System.Windows.Automation.PropertyCondition]::new($auto::AutomationIdProperty, $id)
    $until = (Get-Date).AddSeconds($seconds)
    do {
        # The tree may be rebuilt under the search - a section was just pressed - and the search
        # then breaks instead of finding nothing: asked again like any other "not yet".
        $found = $null
        try { $found = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition) } catch { }
        if ($found) { return $found }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $until)
    return $null
}
function Press($element) {
    if ($null -eq $element) { throw 'nothing to press' }
    $pattern = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { $pattern.Invoke(); return }
    if ($element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) { $pattern.Toggle(); return }
    throw 'the element can be neither invoked nor toggled'
}
function PressAlive($root, [string]$id) {
    # A button of the work zone comes alive a moment after the run before ends: pressed once it can be.
    $button = Find $root $id 10
    if ($null -eq $button) { throw "no $id in the window" }
    $until = (Get-Date).AddSeconds(10)
    while (-not $button.Current.IsEnabled -and (Get-Date) -lt $until) { Start-Sleep -Milliseconds 100 }
    Press $button
}
function IsOn($element) {
    $pattern = $null
    if (-not $element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) { return $false }
    return $pattern.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On
}
function ValueOf($element) {
    if ($null -eq $element) { return '' }
    $value = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$value)) { return $value.Current.Value }
    return $element.Current.Name
}
function TextOf($root, [string]$id) { ValueOf (Find $root $id 5) }
function Shown($root, [string]$id) {
    # One look, no waiting: a control that is hidden is not in the tree at all.
    try { return $null -ne $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.PropertyCondition]::new($auto::AutomationIdProperty, $id)) }
    catch { return $false }
}
function Outcome($root) {
    # How a run ended is read from the status line, in either language, and a run that goes - from STOP,
    # which is in sight only then.
    $line = TextOf $root 'StatusText'
    if ($line -match '^(Готово|Done): ') { return 'done' }
    if ($line -match '^(Остановлено|Stopped): ') { return 'stopped' }
    if ($line -match ': (отказ до начала|refused before it began)') { return 'refused' }
    if ($line -match ': (ошибка|failed) - ') { return 'failed' }
    if (Shown $root 'stop') { return 'running' }
    return ''
}
function WaitOutcome($root, [string]$wanted, [int]$seconds, [string]$before = '') {
    # $before: the status line before the press - an outcome of the run before is not this run's.
    $until = (Get-Date).AddSeconds($seconds)
    do {
        $now = Outcome $root
        if ($now -eq $wanted -and ($wanted -eq 'running' -or (TextOf $root 'StatusText') -ne $before)) { return $now }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $until)
    return "$(Outcome $root) <$(TextOf $root 'StatusText')>"
}
function RunAndWait($root, [string]$id, [int]$seconds) {
    $before = TextOf $root 'StatusText'
    PressAlive $root $id
    return WaitOutcome $root 'done' $seconds $before
}
function FindInProcess([int]$id, [string]$name, [int]$seconds = 15) {
    # A question and a menu are windows of their own: looked for among the windows of the process, not inside the main one.
    $mine = [System.Windows.Automation.PropertyCondition]::new($auto::ProcessIdProperty, $id)
    $named = [System.Windows.Automation.PropertyCondition]::new($auto::AutomationIdProperty, $name)
    $until = (Get-Date).AddSeconds($seconds)
    do {
        try {
            foreach ($top in $auto::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $mine)) {
                $found = $top.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $named)
                if ($found) { return $found }
            }
        }
        catch { }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $until)
    return $null
}
function AnswerYes([int]$id, [int]$seconds = 30) {
    # "Yes" of a question that cannot be taken back comes alive a moment after it opens.
    $yes = FindInProcess $id 'AskYes' $seconds
    if (-not $yes) { return $false }
    $until = (Get-Date).AddSeconds(5)
    while (-not $yes.Current.IsEnabled -and (Get-Date) -lt $until) { Start-Sleep -Milliseconds 100 }
    Press $yes
    Start-Sleep -Milliseconds 500
    return $true
}
function SetupLater([int]$id, [string[]]$named, [string[]]$not) {
    # The question of the additional components at the start: the parts named are in it, the others are not; INSTALL
    # LATER ticked shows where SETUP is and turns INSTALL into UNDERSTOOD, which closes it.
    $later = FindInProcess $id 'setup_later' 40
    if (-not $later) { return $false }
    foreach ($part in $named) { if (-not (FindInProcess $id "setup_item_$part" 3)) { return $false } }
    foreach ($part in $not) { if (FindInProcess $id "setup_item_$part" 1) { return $false } }
    Press $later
    Start-Sleep -Milliseconds 400
    $hint = FindInProcess $id 'setup_hint' 5
    if (-not $hint -or $hint.Current.Name -notmatch 'SETUP') { return $false }
    $close = FindInProcess $id 'setup_close' 5
    if (-not $close -or (FindInProcess $id 'setup_install' 1)) { return $false }
    # OPEN SETUP stays in sight whatever the tick says.
    if (-not (FindInProcess $id 'setup_open' 3)) { return $false }
    Press $close
    Start-Sleep -Milliseconds 600
    return -not (FindInProcess $id 'setup_later' 1)
}
function WaitFile([string]$path, [string]$pattern, [bool]$present, [int]$seconds = 15) {
    $until = (Get-Date).AddSeconds($seconds)
    do {
        $text = if (Test-Path -LiteralPath $path) { Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue } else { '' }
        if (($text -match $pattern) -eq $present) { return $true }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $until)
    return $false
}
function LastJournal([string]$like) {
    # The journal of the last run of an operation, as the engine wrote it into the logs of the stand.
    $file = Get-ChildItem -LiteralPath (Join-Path $Stand 'logs') -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like $like } |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if ($file) { return Get-Content -LiteralPath $file.FullName -Raw } else { return '' }
}
function OpenPage($root, [string]$section, [string]$page) {
    Press (Find $root "section_$section" 10)
    $tab = Find $root "page_${section}_$page" 10
    if ($tab) { Press $tab; Start-Sleep -Milliseconds 600 }
    return $null -ne (Find $root "run_$page" 10)
}
function Videos([string]$folder) { @(FilesIn $folder | Where-Object { $_.Extension -in '.mp4', '.mkv', '.mov' -and $_.Name -notlike '*.writing-*' }) }
function StartWindow([string]$card = '') {
    $env:AUDION_WALK = '1'
    # A card of the walk, or none: a machine with an NVIDIA RTX card tells the window its own, so "0" says there is none.
    $env:AUDION_VS_RTX = if ($card) { $card } else { '0' }
    try { $process = Start-Process -FilePath $exe -PassThru }
    finally { Remove-Item Env:\AUDION_WALK, Env:\AUDION_VS_RTX -ErrorAction SilentlyContinue }
    # A window with no button on the taskbar is no "main window" to .NET: it is looked for among the
    # windows of the desktop by the id of its process.
    $mine = [System.Windows.Automation.PropertyCondition]::new($auto::ProcessIdProperty, $process.Id)
    $until = (Get-Date).AddSeconds(40)
    do {
        $found = $null
        try { $found = $auto::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children, $mine) } catch { }
        if ($found) { $script:root = $found; return $process }
        Start-Sleep -Milliseconds 300
    } while (-not $process.HasExited -and (Get-Date) -lt $until)
    throw $(if ($process.HasExited) { "the window ended at its start, exit code $($process.ExitCode)" } else { 'the window did not open' })
}
function SlideTo($element, [double]$value) {
    $pattern = $null
    if (-not $element.TryGetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern, [ref]$pattern)) { throw 'the slider has no range' }
    $pattern.SetValue($value)
}
function WaitText($root, [string]$id, [string]$pattern, [int]$seconds) {
    $until = (Get-Date).AddSeconds($seconds)
    do {
        $text = TextOf $root $id
        if ($text -match $pattern) { return $text }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $until)
    return $text
}
function CloseWindow($root) {
    $close = $null
    [void]$root.TryGetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern, [ref]$close)
    $close.Close()
}

try {
    foreach ($n in 1..3) { MakeClip "clip_$n.mp4" 2 '640x360' }
    $process = StartWindow
    $bounds = $root.Current.BoundingRectangle
    Say ($bounds.Right -le 0 -or $bounds.Bottom -le 0) ("the window of the walk stands off the screen: {0},{1}" -f $bounds.Left, $bounds.Top)

    $tab = Find $root 'section_precision' 40
    Say ($null -ne $tab) 'the layout is read: the palette PRECISION is in the window'
    Press (Find $root 'section_restoration' 10)
    Say ($null -ne (Find $root 'page_restoration_qtgmc_deinterlace' 10) -and -not (Shown $root 'page_restoration_dpir_denoise')) 'without an RTX card the neural presets are not in RESTORATION'
    Say (OpenPage $root 'precision' 'deband_safe') 'PRECISION -> deband_safe: its page is in sight with RUN'
    Say (-not (Shown $root 'engine_install_vapoursynth')) 'the engine of the stand is found: no card asks to install it'
    Say (-not (FindInProcess $process.Id 'setup_later' 2)) 'every component in place: no question of the additional components at the start'

    # SETUP of the header: the sheet of the components, and back.
    Press (Find $root 'setup' 10)
    Say ($null -ne (Find $root 'update_vapoursynth' 10) -and $null -ne (Find $root 'update_ffmpeg' 3) -and -not (Shown $root 'setup_install_missing')) 'SETUP: the components with their buttons, nothing to install'
    Press (Find $root 'setup' 10)
    Start-Sleep -Milliseconds 400
    Say ($null -ne (Find $root 'section_precision' 10)) 'SETUP pressed again: the sections are back'

    # The cards of the encoder: MKV of x.264 goes to the form server and comes back on.
    $mkv = Find $root 'field_encode_container_mkv' 15
    if ($mkv) { Press $mkv; Start-Sleep -Milliseconds 600 }
    $mkv = Find $root 'field_encode_container_mkv' 5
    Say ($null -ne $mkv -and (IsOn $mkv)) 'the card x.264: MKV pressed and on'

    # The slider of a number: one step up, told to the form server and back in the box.
    $was = 0.0; $now = 0.0
    [void][double]::TryParse((TextOf $root 'field_range'), [ref]$was)
    SlideTo (Find $root 'slide_range' 10) ($was + 1)
    Start-Sleep -Milliseconds 900
    [void][double]::TryParse((TextOf $root 'field_range'), [ref]$now)
    Say ($now -eq $was + 1) "the slider of the number Range: $was -> $now"

    # The preview under the form: the middle frame of the first video, before and after, counted by itself.
    $counted = WaitText $root 'preview_state' '^(Посчитано|Counted)' 60
    Say ($counted -match '^(Посчитано|Counted)') "the preview counts the middle frame by itself: $counted"
    $count = TextOf $root 'preview_count'
    $facts = TextOf $root 'preview_facts'
    Say ($count -eq '1 / 3' -and $facts -match '640 × 360' -and $facts -match '(кадр|frame) 25 ') "the preview: video $count, $($facts -replace '\s+', ' ')"
    Press (Find $root 'preview_next' 10)
    $named = WaitText $root 'preview_name' 'clip_2' 10
    $counted = WaitText $root 'preview_state' '^(Посчитано|Counted)' 60
    Say ($named -eq 'clip_2.mp4' -and (TextOf $root 'preview_count') -eq '2 / 3' -and $counted -match '^(Посчитано|Counted)') "the next video of the Source in the preview: $named, $counted"

    # COMMAND: the commands of vspipe and FFmpeg are said in the journal, nothing is written.
    $state = RunAndWait $root 'dry_deband_safe' 60
    $said = LastJournal '*deband_safe.log'
    Say ($state -eq 'done' -and (FilesIn $out).Count -eq 0 -and $said -match '\[DRY RUN\] 3 file') "COMMAND: $state, the journal says the commands, files in output: $((FilesIn $out).Count)"

    # RUN of the preset: every clip into MKV, in the folder of the palette and of the preset.
    $state = RunAndWait $root 'run_deband_safe' 240
    $made = FilesIn $out
    $mkvs = @($made | Where-Object { $_.Extension -eq '.mkv' -and $_.Name -notlike '*.writing-*' -and $_.FullName -like '*\Precision\deband_safe_*' -and $_.Length -gt 10KB })
    Say ($state -eq 'done' -and $mkvs.Count -eq 3 -and $made.Count -eq 3) "RUN of the preset: $state, MKV in output\Precision\deband_safe_*: $($mkvs.Count) of 3 ($($made.Count) files)"
    $log = @(Get-ChildItem -LiteralPath (Join-Path $Stand 'logs') -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '*deband_safe*' })
    Say ($log.Count -ge 2) "the runs went through the console command: their journals lie in the logs of the stand ($($log.Count))"

    # LIST and DETAILS of the work zone: the videos a run takes, and what ffprobe knows of them.
    $state = RunAndWait $root 'route_list' 60
    Say ($state -eq 'done' -and (LastJournal '*source_list.log') -match '\[LIST\] 3 video') "LIST: $state, three videos of the Source in the journal"
    $state = RunAndWait $root 'route_details' 60
    $probed = [regex]::Matches((LastJournal '*probe_source.log'), '\[PROBE\] clip_\d\.mp4 \| 640x360 \| 25\.0 fps').Count
    Say ($state -eq 'done' -and $probed -eq 3) "DETAILS: $state, ffprobe said $probed of 3 as 640x360 25 fps"

    # SAVE AS PROFILE: the name is asked, the preset with the values of its page goes into config\profiles.
    PressAlive $root 'own_profile_save'
    $box = FindInProcess $process.Id 'ask_value' 15
    $named = ValueOf $box
    Say ($named -eq 'deband_safe_mine') "SAVE AS PROFILE asks the name of the profile: $named"
    Say (AnswerYes $process.Id) 'the name answered'
    Say (WaitFile $profile '"preset":\s*"deband_safe"' $true 30) 'config\profiles\deband_safe_mine.json holds the preset deband_safe'
    Start-Sleep -Milliseconds 800

    # The profile on PROFILES: among the choices, and its run on the Source.
    Say (OpenPage $root 'profiles' 'profile_run') 'PROFILES: its page is in sight with RUN'
    $mine = Find $root 'field_profile_deband_safe_mine' 15
    if ($mine) { Press $mine; Start-Sleep -Milliseconds 600 }
    $mine = Find $root 'field_profile_deband_safe_mine' 5
    Say ($null -ne $mine -and (IsOn $mine)) 'PROFILES: the saved profile is among the choices, pressed and on'
    $state = RunAndWait $root 'run_profile_run' 240
    $runs = Videos (Join-Path $out 'Profiles')
    Say ($state -eq 'done' -and $runs.Count -eq 3 -and @($runs | Where-Object { $_.FullName -like '*\Profiles\deband_safe_mine_*' }).Count -eq 3) "the run of the profile: $state, videos in output\Profiles\deband_safe_mine_*: $($runs.Count) of 3"

    # The pin of the Source: kept in the history of the stand, and taken off again.
    $history = Join-Path $Stand 'config\path_history.json'
    Press (Find $root 'route_pin_source' 15)
    Say (WaitFile $history '"pinned":\s*true' $true) 'the pin of the Source: config\path_history.json holds a pinned path'
    Press (Find $root 'route_pin_source' 15)
    Say (WaitFile $history '"pinned":\s*true' $false) 'pressed again: no path is pinned'

    # TO SOURCE: the Source is cleared, the result moves into it with its folders, the Target is left empty.
    $results = (FilesIn $out).Count
    PressAlive $root 'route_to_source'
    Say (AnswerYes $process.Id) 'TO SOURCE asks first'
    $until = (Get-Date).AddSeconds(20)
    while ((FilesIn $out).Count -gt 0 -and (Get-Date) -lt $until) { Start-Sleep -Milliseconds 300 }
    Start-Sleep -Milliseconds 500
    Say ((FilesIn $out).Count -eq 0 -and (FilesIn $in).Count -eq $results -and $results -eq 6) "TO SOURCE: output is empty, input holds the $results results ($((FilesIn $in).Count))"

    # CLEAR: its menu, the question, the contents gone and the folders left - to the Recycle Bin.
    Set-Content -LiteralPath (Join-Path $out 'release-walk-probe.txt') -Value 'a probe of release-walk.ps1' -Encoding utf8
    PressAlive $root 'route_clear'
    $both = Find $root 'clear_both' 5
    if (-not $both) { $both = FindInProcess $process.Id 'clear_both' 10 }
    Say ($null -ne $both) 'the button CLEAR opens its menu: "both" is in it'
    if ($both) {
        Press $both
        Say (AnswerYes $process.Id) 'CLEAR asks first'
        # A folder outside the program is asked about once more; the stand's are its own.
        [void](AnswerYes $process.Id 2)
        $until = (Get-Date).AddSeconds(20)
        do { Start-Sleep -Milliseconds 300; $left = (FilesIn $in).Count + (FilesIn $out).Count } while ($left -gt 0 -and (Get-Date) -lt $until)
        Say ($left -eq 0 -and (Test-Path -LiteralPath $in) -and (Test-Path -LiteralPath $out)) "CLEAR: the contents of input and output are gone, the folders stay ($left left)"
    }

    # RUN on an empty Source: refused before it began, the reason in the terminal, nothing written.
    Start-Sleep -Milliseconds 600
    [void](OpenPage $root 'precision' 'deband_safe')
    $before = TextOf $root 'StatusText'
    PressAlive $root 'run_deband_safe'
    $state = WaitOutcome $root 'refused' 30 $before
    $said = LastJournal '*deband_safe.log'
    Say ($state -eq 'refused' -and (FilesIn $out).Count -eq 0 -and $said -match '\[REFUSED\]' -and $said -notmatch 'Traceback') "RUN on an empty Source: $state, one line [REFUSED], no trace"

    # STOP while BM3D on the processor goes over a minute of 1080p.
    MakeClip 'long.mp4' 60 '1920x1080'
    Say (OpenPage $root 'precision' 'shadow_denoise_sota') 'PRECISION -> shadow_denoise_sota: its page is in sight with RUN'
    $cpu = Find $root 'field_vs_accel_cpu' 15
    if ($cpu) { Press $cpu; Start-Sleep -Milliseconds 600 }
    $cpu = Find $root 'field_vs_accel_cpu' 5
    Say ($null -ne $cpu -and (IsOn $cpu)) 'BM3D: the processor pressed and on'
    $run = Find $root 'run_shadow_denoise_sota' 10
    Say ($null -ne $run -and $run.Current.IsEnabled) 'RUN is there and can be pressed'
    Press $run
    $state = WaitOutcome $root 'running' 15
    Say ($state -eq 'running') "a minute of 1080p through BM3D on the processor: the operation goes ($state)"
    $until = (Get-Date).AddSeconds(90)
    while (-not (FilesIn $out | Where-Object { $_.Name -like '*.writing-*' -and $_.Length -gt 0 }) -and (Get-Date) -lt $until) { Start-Sleep -Milliseconds 300 }
    $writing = @(FilesIn $out | Where-Object { $_.Name -like '*.writing-*' })
    Say ($writing.Count -eq 1) "FFmpeg writes under a name of its own while it goes: $(($writing | ForEach-Object Name) -join ', ')"
    $until = (Get-Date).AddSeconds(30)
    do { $live = TextOf $root 'ActivityText'; if ($live -match '\d+%') { break }; Start-Sleep -Milliseconds 300 } while ((Get-Date) -lt $until)
    Say ($live -match '^(Обработка|Processing): \d+%.*long\.mp4') "the live line over the journal: $live"
    $stop = Find $root 'stop' 5
    Say ($null -ne $stop -and $stop.Current.IsEnabled) 'STOP is in sight and can be pressed while the operation goes'
    $clock = [System.Diagnostics.Stopwatch]::StartNew()
    Press $stop
    $state = WaitOutcome $root 'stopped' 70
    $took = [Math]::Round($clock.Elapsed.TotalSeconds, 1)
    Say ($state -eq 'stopped' -and $took -lt 30) "STOP pressed: $state in $took s"
    Start-Sleep -Milliseconds 800
    $left = FilesIn $out
    Say ($left.Count -eq 0) "no half-written file is left in output: $(($left | ForEach-Object Name) -join ', ')"
    $said = LastJournal '*shadow_denoise_sota.log'
    Say ($said -match '\[STOPPED\]' -and $said -notmatch 'Traceback') 'the journal says [STOPPED] in one line, no trace'
    Start-Sleep -Milliseconds 600
    Say ($run.Current.IsEnabled) 'after the stop RUN can be pressed again'

    # The window closed while the operation goes: it asks, stops the operation and then closes.
    Press $run
    $null = WaitOutcome $root 'running' 15
    Start-Sleep -Seconds 5
    CloseWindow $root
    $asked = AnswerYes $process.Id 15
    Say $asked 'closing during an operation asks first'
    Say ($process.WaitForExit(90000)) 'answered: the operation stopped and the window closed'
    Start-Sleep -Seconds 1
    $left = FilesIn $out
    Say ($left.Count -eq 0) "closed in the middle: no half-written file in output ($(($left | ForEach-Object Name) -join ', '))"

    # The window once more, told of an NVIDIA RTX card: the neural presets and the installation of MLRT.
    Start-Sleep -Seconds 1
    $process = StartWindow 'NVIDIA GeForce RTX 5070 (walk)'
    Say ($null -ne (Find $root 'section_restoration' 40)) 'with an RTX card: the window opens'
    Say (SetupLater $process.Id @('mlrt') @('vapoursynth', 'plugins', 'ffmpeg')) 'with an RTX card and no MLRT the start offers MLRT; INSTALL LATER says where SETUP is'
    Press (Find $root 'section_restoration' 10)
    $neural = Find $root 'page_restoration_dpir_denoise' 15
    Say ($null -ne $neural) 'with an RTX card: DPIR Denoise is among the presets of RESTORATION'
    if ($neural) { Press $neural; Start-Sleep -Milliseconds 800 }
    Say ($null -ne (Find $root 'engine_install_mlrt' 15)) 'without MLRT its page shows the installation of MLRT'
    Press (Find $root 'setup' 10)
    Say ($null -ne (Find $root 'update_mlrt' 10) -and $null -ne (Find $root 'setup_install_missing' 3)) 'with an RTX card SETUP offers MLRT and INSTALL ALL'
    CloseWindow $root
    Say ($process.WaitForExit(30000)) 'the window with the card closed'

    # The window once more with the engine of the stand put aside: VapourSynth and its plugins are not there.
    $engine = Join-Path $Stand 'system_core\vapoursynth'
    $aside = "$engine.walk-aside"
    Start-Sleep -Seconds 1
    Rename-Item -LiteralPath $engine -NewName (Split-Path -Leaf $aside)
    try {
        $process = StartWindow
        Say ($null -ne (Find $root 'section_precision' 40)) 'without the engine: the window opens'
        Say (SetupLater $process.Id @('vapoursynth', 'plugins') @('ffmpeg', 'mlrt')) 'without the engine the start offers VapourSynth and its plugins, FFmpeg is in place'
        Press (Find $root 'setup' 10)
        $all = Find $root 'setup_install_missing' 10
        Say ($null -ne $all) 'without the engine SETUP offers INSTALL ALL'
        if ($all) {
            Press $all
            $cancel = FindInProcess $process.Id 'setup_cancel' 20
            Say ($null -ne $cancel -and $null -ne (FindInProcess $process.Id 'setup_item_vapoursynth' 3)) 'INSTALL ALL asks first, with what will be installed'
            if ($cancel) { Press $cancel; Start-Sleep -Milliseconds 500 }
        }
        CloseWindow $root
        Say ($process.WaitForExit(30000)) 'the window without the engine closed'
    }
    finally {
        Start-Sleep -Seconds 1
        Rename-Item -LiteralPath $aside -NewName (Split-Path -Leaf $engine)
    }

    Start-Sleep -Seconds 2
    $alive = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Stand, [StringComparison]::OrdinalIgnoreCase) })
    Say ($alive.Count -eq 0) ("no process of the stand is left: {0}" -f (($alive | ForEach-Object Name) -join ', '))
    $crash = @(Get-ChildItem -LiteralPath (Join-Path $Stand 'logs') -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'gui-crash-*' -or ($_.Name -eq 'gui-event-errors.log' -and $_.Length -gt 0) })
    Say ($crash.Count -eq 0) ("the window wrote no report of its own errors: {0}" -f (($crash | ForEach-Object Name) -join ', '))
}
catch {
    Say $false ("the walk broke: " + $_.Exception.Message)
}
finally {
    Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($Stand, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { try { $_.Kill($true) } catch { } }
    if ($Keep) { "the stand is kept: $Stand" }
    else {
        Start-Sleep -Milliseconds 800
        # The stand is a plain copy - no link of it leads into the program - so it goes whole.
        [System.IO.Directory]::Delete($Stand, $true)
        'the stand is removed'
    }
}
"failed checks: $failed"
exit $(if ($failed) { 1 } else { 0 })
