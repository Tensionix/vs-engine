<#
.SYNOPSIS
  Audion VS Engine - Install vs-mlrt TensorRT bundle (Phase 18.B-ML).

.DESCRIPTION
  Phase 18.B-ML installer. Brings ONNX inference into VapourSynth so we can
  ship Real-ESRGAN super-resolution, RIFE frame interpolation and DPIR
  ML-denoise as preset scripts.

  We bundle the FULL TensorRT package -- biggest, fastest, all-batteries:

    vsmlrt-windows-x64-tensorrt.v15.16.7z (split, ~2.7 GB compressed,
                                           ~5 GB extracted)

  This single archive includes EVERY backend so a single install covers all
  hardware paths:
    - VSTRT (TensorRT, NVIDIA-only)  -- fastest inference on RTX 20+/30/40/50
    - VSORT (ONNX Runtime, CPU + DirectML EP) -- universal fallback for
      Intel Xe / AMF / NVIDIA via DirectML 12
    - VSOV  (OpenVINO, Intel-tuned)  -- extracted, then quarantined by Audion
      outside VapourSynth autoload because OpenVINO DLLs can trigger Windows
      Code Integrity / "Bad Image" 0xc0e90002 on some hosts
    - VSNCNN (NCNN, Vulkan)          -- mobile-style fallback
    - TensorRT runtime libraries     -- needed by VSTRT
    - ONNX Runtime DLLs              -- needed by VSORT

  Plus we download:
    scripts.7z  (~50 KB)            -- vsmlrt.py + helpers
    models.7z   (~850 MB compressed,
                 ~1 GB extracted)   -- full ONNX model collection

  Total install layer addition: ~6 GB extracted on top of existing ~3.2 GB
  project (release goes to ~9 GB). Justified by "all-in-one Nuke-package"
  philosophy and explicit user choice ("Места не жалеем!").

  Multi-volume .7z extraction: vs-mlrt's TensorRT bundle ships split into
  .7z.001 + .7z.002 because GitHub's 2 GB asset cap. We use the official
  7zr.exe standalone command-line tool from 7-zip.org -- ~1.5 MB binary that
  handles BCJ2-filtered archives (x86 binary preprocessor) which py7zr
  cannot. py7zr fails on vs-mlrt archives because the included TensorRT
  runtime DLLs are stored with BCJ2 compression for better ratio. 7zr.exe
  also handles multi-volume archives natively when given the .001 part.

  Backend selection at runtime: handled by vsmlrt.Backend.* in each .vpy
  preset. We try TRT -> ORT_DML -> ORT_CPU in that order. The OpenVINO/vsov
  backend is not part of the default active autoload set; it is kept under
  system_core\vapoursynth\disabled_plugins\vsmlrt-openvino for manual restore.

.PARAMETER ProjectRoot
  Absolute path to project root.

.PARAMETER MLRTVersion
  Optional vs-mlrt release tag (e.g. "v15.16"). If empty -> resolve latest
  from https://api.github.com/repos/AmusementClub/vs-mlrt/releases/latest.

.PARAMETER NoModels
  Skip downloading the models pack (~852 MB). Presets won't run without
  models -- only useful for CI / headless setups that bring their own.

.PARAMETER Force
  Deprecated compatibility switch. The installer always refreshes MLRT.

.PARAMETER Lean
  Trim installed bundle to only what runs on the local hardware. After a
  full extract this:
    - keeps `nvinfer_builder_resource_sm<X>_10.dll` matching the GPU's
      compute capability (queried from nvidia-smi) and the ptx fallback;
      removes other-SM resources (~1 GB savings)
    - removes models for which we have no preset (cugan, waifu2x,
      ~150 MB savings)
  Smoke-test still runs after trim so a misdetection surfaces immediately.

.PARAMETER DropCache
  After a successful install + smoke test, call the central
  Clean-Install-Cache policy for transient install downloads, staging dirs,
  and bytecode caches. Re-install may require re-download. Combined with
  -Lean this brings total disk footprint from ~10 GB to ~3.5 GB.
#>
param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [string]$MLRTVersion = "",
    [switch]$NoModels,
    [switch]$Force,
    [switch]$Lean,
    [switch]$DropCache
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

$VSDir       = Join-Path $ProjectRoot 'system_core\vapoursynth'
$VSPython    = Join-Path $VSDir 'python.exe'
$VSScriptDir  = Join-Path $VSDir 'vs-scripts'
$DLDir        = Join-Path $ProjectRoot 'install\download'
$Marker       = Join-Path $VSDir '.audion-mlrt.marker'
$Headers      = @{ 'User-Agent' = 'Audion-VS-Engine' }
# A token lifts the GitHub limit from 60 requests an hour to 5000; without one
# a full pattern run exhausts it and downloads start failing halfway.
if ($env:GITHUB_TOKEN) { $Headers['Authorization'] = 'Bearer ' + $env:GITHUB_TOKEN }
if (-not (Test-Path $VSPython)) {
    throw "VS-host Python not found at $VSPython. Run Install-Portable-VapourSynth.cmd first."
}

# VapourSynth R74+ Python wheel layout auto-scans the directory returned by
# vapoursynth.get_plugin_dir(). The old standalone vs-plugins\ folder at VS
# root is legacy and is not the authoritative target anymore. Keep MLRT under
# a dedicated `vsmlrt\` subdir so its runtime DLLs and models stay grouped
# (vsmlrt.py looks for models at <vstrt.dll's-dir>\models\<modelname>\).
$pluginRootProbe = (& $VSPython -c "import vapoursynth; print(vapoursynth.get_plugin_dir())" 2>$null | Select-Object -Last 1)
if ([string]::IsNullOrWhiteSpace($pluginRootProbe)) {
    $VSPluginRoot = Join-Path $VSDir 'Lib\site-packages\vapoursynth\plugins'
} else {
    $VSPluginRoot = $pluginRootProbe.Trim()
}
$VSPluginDir = Join-Path $VSPluginRoot 'vsmlrt'
$DisabledPluginDir = Join-Path $VSDir 'disabled_plugins\vsmlrt-openvino'

foreach ($d in @($VSPluginRoot, $VSPluginDir, $VSScriptDir, $DLDir)) {
    if (-not (Test-Path $d)) { New-Item -Path $d -ItemType Directory -Force | Out-Null }
}

function Disable-MLRTOpenVINOBackend {
    param(
        [Parameter(Mandatory=$true)][string]$PluginDir,
        [Parameter(Mandatory=$true)][string]$QuarantineDir
    )

    $vsovDir = Join-Path $PluginDir 'vsov'
    $vsovDll = Join-Path $PluginDir 'vsov.dll'

    if (-not (Test-Path $vsovDir) -and -not (Test-Path $vsovDll)) {
        Write-Host "      [mlrt] OpenVINO backend not present; nothing to quarantine"
        return
    }

    if (Test-Path $QuarantineDir) {
        Remove-Item -LiteralPath $QuarantineDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -Path $QuarantineDir -ItemType Directory -Force | Out-Null

    if (Test-Path $vsovDir) {
        Move-Item -LiteralPath $vsovDir -Destination (Join-Path $QuarantineDir 'vsov') -Force
        Write-Host "      [mlrt] quarantined OpenVINO runtime dir: vsov"
    }
    if (Test-Path $vsovDll) {
        Move-Item -LiteralPath $vsovDll -Destination (Join-Path $QuarantineDir 'vsov.dll.disabled') -Force
        Write-Host "      [mlrt] quarantined OpenVINO plugin: vsov.dll"
    }

    @(
        'Audion policy: OpenVINO/vsov is quarantined outside VapourSynth autoload.',
        'Reason: OpenVINO runtime DLLs can trigger Windows Code Integrity / Bad Image 0xc0e90002 on some hosts.',
        'TensorRT / TensorRT-RTX / ONNX Runtime MLRT backends remain installed under the active vsmlrt plugin dir.',
        'To re-enable manually, move vsov\ back and rename vsov.dll.disabled to vsov.dll in the active vsmlrt plugin dir.'
    ) | Set-Content -Path (Join-Path $QuarantineDir 'README.txt') -Encoding UTF8
}

Write-Host "======================================================================"
Write-Host "  AUDION VS ENGINE - INSTALL VS-MLRT (TensorRT bundle, Phase 18.B-ML)"
Write-Host "======================================================================"
Write-Host "VS dir:       $VSDir"
Write-Host "VS Python:    $VSPython"
Write-Host "Plugins dir:  $VSPluginDir"
Write-Host "Disabled dir: $DisabledPluginDir"
Write-Host "Scripts dir:  $VSScriptDir"
Write-Host ("Mode:         {0}{1}" -f
    $(if ($Lean) { 'LEAN (trim to local GPU)' } else { 'FULL bundle' }),
    $(if ($DropCache) { ' + DROP-CACHE (central install cache cleanup after success)' } else { '' }))
Write-Host ""
Write-Host "Note: download is ~3.5 GB compressed; full extract ~6 GB."
Write-Host "      With -Lean -DropCache final footprint is ~3.5 GB."
Write-Host ""

# ---------- 1. Bootstrap 7zr.exe (official 7-Zip standalone CLI) ----------
# vs-mlrt archives contain native x86 binaries (TensorRT runtime DLLs)
# compressed with the BCJ2 filter -- py7zr cannot decode it
# (UnsupportedCompressionMethodError on `\x03\x03\x01\x1b` method id).
# 7zr.exe handles all 7z filters including BCJ2 and natively reads
# multi-volume archives.
. (Join-Path $PSScriptRoot 'Ensure-7zip.ps1')

Write-Host "[1/6] Ensuring 7zr.exe (.7z extraction with BCJ2 support) is available..."
$Bin7z = Ensure-7zr -ProjectRoot $ProjectRoot
$ver7z = & $Bin7z 2>&1 | Select-Object -First 2
Write-Host "      [OK] 7zr.exe ready: $($ver7z -join ' / ')"

# ---------- 2. Resolve release ----------
if ([string]::IsNullOrWhiteSpace($MLRTVersion)) {
    Write-Host "[2/6] Resolving latest vs-mlrt release..."
    $rel = Invoke-RestMethod -Headers $Headers -Uri 'https://api.github.com/repos/AmusementClub/vs-mlrt/releases/latest'
    $MLRTVersion = $rel.tag_name
} else {
    Write-Host "[2/6] Using pinned vs-mlrt version $MLRTVersion..."
    $rel = Invoke-RestMethod -Headers $Headers -Uri "https://api.github.com/repos/AmusementClub/vs-mlrt/releases/tags/$MLRTVersion"
}
Write-Host "      vs-mlrt: $MLRTVersion"

Write-Host "      Policy: fresh MLRT download + clean install target every run."

# ---------- 3. Pick assets ----------
function Find-Assets($pattern) {
    $list = $rel.assets | Where-Object { $_.name -like $pattern } | Sort-Object name
    if ($list.Count -eq 0) { throw "No asset matching '$pattern' in $MLRTVersion release" }
    return ,$list
}

# TensorRT bundle is split into .7z.001 and .7z.002 (GitHub 2GB asset cap)
$assetsTRT    = Find-Assets 'vsmlrt-windows-x64-tensorrt*.7z.*'
$assetScripts = (Find-Assets 'scripts*.7z')[0]
$assetModels  = if (-not $NoModels) { (Find-Assets 'models*.7z')[0] } else { $null }

Write-Host "      Will download:"
foreach ($a in $assetsTRT) {
    Write-Host ("        - {0,-60} {1,8:N1} MB" -f $a.name, ($a.size / 1MB))
}
Write-Host ("        - {0,-60} {1,8:N1} MB" -f $assetScripts.name, ($assetScripts.size / 1MB))
if ($assetModels) {
    Write-Host ("        - {0,-60} {1,8:N1} MB" -f $assetModels.name, ($assetModels.size / 1MB))
}

# ---------- 4. Download ----------
$ProgressPreference = 'Continue'
function Get-FileSizeOrZero($path) {
    if (Test-Path -LiteralPath $path) {
        return [int64](Get-Item -LiteralPath $path).Length
    }
    return [int64]0
}

function Invoke-ResumableAssetDownload($asset, $tmpDest) {
    $url = $asset.browser_download_url

    # Large GitHub assets (2 GB split volumes) sometimes terminate mid-stream.
    # Prefer curl because `-C -` resumes a .part file after redirects and gives
    # stronger retry controls than Invoke-WebRequest. Keep IWR as a fallback
    # for minimal Windows images where curl.exe was removed.
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($curl) {
        & $curl.Source `
            --location `
            --fail `
            --retry 8 `
            --retry-all-errors `
            --retry-delay 5 `
            --connect-timeout 30 `
            --speed-time 60 `
            --speed-limit 1024 `
            --continue-at - `
            --output $tmpDest `
            $url
        if ($LASTEXITCODE -ne 0) {
            throw "curl.exe failed downloading $($asset.name) (exit $LASTEXITCODE)"
        }
        return
    }

    $iwr = Get-Command Invoke-WebRequest
    $iwrParams = @{
        Headers = $Headers
        Uri     = $url
        OutFile = $tmpDest
    }
    if ($iwr.Parameters.ContainsKey('Resume')) {
        $iwrParams.Resume = $true
    }
    Invoke-WebRequest @iwrParams
}

function Get-FreshAsset($asset, $dest) {
    $tmpDest = "$dest.part"
    $expected = [int64]$asset.size

    $readySize = Get-FileSizeOrZero $dest
    if ($readySize -eq $expected) {
        Write-Host "      [cache] $($asset.name) already complete ($readySize bytes)"
        return
    } elseif ($readySize -gt 0) {
        Write-Host "      [cache] removing incomplete final $($asset.name) ($readySize / $expected bytes)"
        Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
    }

    $partialSize = Get-FileSizeOrZero $tmpDest
    if ($partialSize -gt $expected) {
        Write-Host "      [cache] removing oversized partial $($asset.name) ($partialSize / $expected bytes)"
        Remove-Item -LiteralPath $tmpDest -Force -ErrorAction SilentlyContinue
        $partialSize = 0
    } elseif ($partialSize -eq $expected) {
        if (Test-Path -LiteralPath $dest) {
            Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
        }
        Move-Item -LiteralPath $tmpDest -Destination $dest -Force
        Write-Host "      [OK] $($asset.name) recovered from complete .part ($expected bytes)"
        return
    }

    if ($partialSize -gt 0) {
        Write-Host "      Resuming $($asset.name) ($([math]::Round($partialSize/1MB,1)) / $([math]::Round($expected/1MB,1)) MB) ..."
    } else {
        Write-Host "      Downloading fresh $($asset.name) ($([math]::Round($expected/1MB,1)) MB) ..."
    }

    $maxAttempts = 8
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            if ($attempt -gt 1) {
                $cur = Get-FileSizeOrZero $tmpDest
                Write-Host "      Retry $attempt/$maxAttempts for $($asset.name) ($([math]::Round($cur/1MB,1)) / $([math]::Round($expected/1MB,1)) MB) ..."
            }

            Invoke-ResumableAssetDownload $asset $tmpDest
            $sz = Get-FileSizeOrZero $tmpDest
            if ($sz -eq $expected) {
                if (Test-Path -LiteralPath $dest) {
                    Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
                }
                Move-Item -LiteralPath $tmpDest -Destination $dest -Force
                Write-Host "      [OK] $($asset.name) ($sz bytes)"
                return
            }
            if ($sz -gt $expected) {
                Remove-Item -LiteralPath $tmpDest -Force -ErrorAction SilentlyContinue
                throw "Downloaded size too large for $($asset.name): got $sz, expected $expected"
            }
            throw "Downloaded size mismatch for $($asset.name): got $sz, expected $expected"
        } catch {
            if ($attempt -ge $maxAttempts) {
                throw
            }
            $delay = [math]::Min(60, 5 * $attempt)
            Write-Warning "Download attempt $attempt failed for $($asset.name): $($_.Exception.Message)"
            Write-Host "      Keeping .part for resume; retrying in $delay sec..."
            Start-Sleep -Seconds $delay
        }
    }
}

Write-Host "[3/6] Downloading vs-mlrt artifacts (this is the slow step)..."
$pathScripts = Join-Path $DLDir $assetScripts.name
Get-FreshAsset $assetScripts $pathScripts

# Get download paths for the TRT split parts (sorted, .001 first)
$trtPaths = @()
foreach ($a in $assetsTRT) {
    $p = Join-Path $DLDir $a.name
    Get-FreshAsset $a $p
    $trtPaths += $p
}
$trtFirst = $trtPaths[0]   # the .001 part (sorted ASCII)

if ($assetModels) {
    $pathModels = Join-Path $DLDir $assetModels.name
    Get-FreshAsset $assetModels $pathModels
}
$ProgressPreference = 'SilentlyContinue'

# ---------- 5. Extract ----------
# All .7z extraction goes through the official 7zr.exe bootstrapped above:
# - handles BCJ2-filtered streams (TensorRT runtime DLLs) which py7zr cannot
# - auto-detects multi-volume archives when given the .001 part
function Extract-Single7z($archive, $target) {
    & $Bin7z x "-o$target" $archive -y -bso0 -bsp1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "7zr.exe failed extracting $archive (exit $LASTEXITCODE)" }
}

function Extract-MultiVolume7z($firstVolume, $target) {
    # 7zr.exe natively reads .7z.001/.7z.002/... when pointed at the .001 part.
    & $Bin7z x "-o$target" $firstVolume -y -bso0 -bsp1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "7zr.exe multi-volume extract failed for $firstVolume (exit $LASTEXITCODE)" }
}

Write-Host "[4/6] Extracting TensorRT bundle (multi-volume; this takes a few minutes)..."
$tmpTRT = Join-Path $VSDir '_mlrt_tmp_trt'
if (Test-Path $tmpTRT) { Remove-Item -Path $tmpTRT -Recurse -Force }
New-Item -Path $tmpTRT -ItemType Directory -Force | Out-Null
Extract-MultiVolume7z $trtFirst $tmpTRT

# Layout detection.
#
# Older vs-mlrt releases shipped the bundle inside a single wrapper folder
# (e.g. "vs-mlrt/"), so we used to descend into it. v15.16 ships FLAT --
# no wrapper, the archive root holds models/, vsmlrt-cuda/, vsort/, vsov/
# plus vstrt.dll / vsort.dll / vsov.dll / vsncnn.dll at the top level.
# Treat $tmpTRT as a wrapper ONLY if it has exactly one directory AND zero
# top-level files; otherwise the archive is already flat. Without this check
# we previously picked "models" (alphabetically first) as the wrapper and
# copied just the model subfolders into vs-plugins/, silently dropping every
# plugin DLL on the floor.
$rootDirs  = @(Get-ChildItem -Path $tmpTRT -Directory)
$rootFiles = @(Get-ChildItem -Path $tmpTRT -File)
if ($rootDirs.Count -eq 1 -and $rootFiles.Count -eq 0) {
    $bundleSrc = $rootDirs[0].FullName
} else {
    $bundleSrc = $tmpTRT
}

Write-Host "      Cleaning MLRT plugin target $VSPluginDir ..."
Get-ChildItem -LiteralPath $VSPluginDir -Force -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "      Copying plugin DLLs + runtime libs to $VSPluginDir ..."
Get-ChildItem -Path $bundleSrc -File | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination (Join-Path $VSPluginDir $_.Name) -Force
}
Get-ChildItem -Path $bundleSrc -Directory | ForEach-Object {
    # Skip a 'models' subfolder if present in bundle (we use the dedicated models pack instead)
    if ($_.Name -ieq 'models') { return }
    Copy-Item -Path $_.FullName -Destination $VSPluginDir -Recurse -Force
}
# Strip files that trigger Windows Defender Application Control because of
# missing/unverifiable code-signing. These are runtime-side helpers, not VS
# plugins, and removing them does not affect any of the supported backends:
#   - openvino_intel_npu_plugin.dll : Intel NPU plugin for OpenVINO. We only
#     ship vsov for Intel CPU/iGPU paths; NPU is a niche path the user
#     wouldn't hit on NVIDIA / DirectML / CPU. Removing it stops the
#     "publisher cannot be verified" pop-up VS triggers when it scans the
#     plugin tree on every fresh box.
$defenderBlockList = @(
    'openvino_intel_npu_plugin.dll'
)
foreach ($name in $defenderBlockList) {
    Get-ChildItem -Path $VSPluginDir -Recurse -Filter $name -ErrorAction SilentlyContinue |
        ForEach-Object {
            Write-Host "      [security] removing unsigned: $($_.FullName)"
            Remove-Item -Path $_.FullName -Force -ErrorAction SilentlyContinue
        }
}

# Blackwell/TensorRT policy: keep MLRT focused on TensorRT / TensorRT-RTX /
# ONNX Runtime paths. OpenVINO/vsov is useful on Intel CPU/iGPU systems, but
# its runtime DLLs can trip Windows Code Integrity / "Bad Image" 0xc0e90002
# during VapourSynth plugin autoload. Quarantine it outside the active
# plugins tree so normal startup and Doctor do not load openvino_auto_plugin.dll.
Disable-MLRTOpenVINOBackend -PluginDir $VSPluginDir -QuarantineDir $DisabledPluginDir

Remove-Item -Path $tmpTRT -Recurse -Force
Write-Host "      [OK] TensorRT bundle extracted"

Write-Host "[5/6] Extracting scripts (vsmlrt.py + helpers)..."
$tmpScripts = Join-Path $VSDir '_mlrt_tmp_scripts'
if (Test-Path $tmpScripts) { Remove-Item -Path $tmpScripts -Recurse -Force }
New-Item -Path $tmpScripts -ItemType Directory -Force | Out-Null
Extract-Single7z $pathScripts $tmpScripts

$scriptsInner = Get-ChildItem -Path $tmpScripts -Directory | Select-Object -First 1
$srcScripts   = if ($scriptsInner) { $scriptsInner.FullName } else { $tmpScripts }

Get-ChildItem -Path $srcScripts -File | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination (Join-Path $VSScriptDir $_.Name) -Force
}
# Also drop vsmlrt.py into VS-host site-packages so `import vsmlrt` works from
# any vspipe script without manipulating sys.path
$sitePkg = Join-Path $VSDir 'Lib\site-packages'
if (Test-Path $sitePkg) {
    $vsmlrtPy = Get-ChildItem -Path $srcScripts -Filter 'vsmlrt.py' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($vsmlrtPy) {
        Copy-Item -Path $vsmlrtPy.FullName -Destination (Join-Path $sitePkg 'vsmlrt.py') -Force
        Write-Host "      [OK] vsmlrt.py also installed to site-packages"
    }
}
Remove-Item -Path $tmpScripts -Recurse -Force
Write-Host "      [OK] scripts extracted"

if ($assetModels) {
    Write-Host "[6/6] Extracting models pack (~850 MB; this takes a minute)..."
    # Models go INTO the plugin dir so vsmlrt.py's lookup `<vstrt's dir>\models\<name>\`
    # resolves. Archive root holds `models\<name>\...`, so extracting into
    # $VSPluginDir lands them at the right relative path automatically.
    $modelsTargetCheck = Join-Path $VSPluginDir 'models'
    if ($Force -and (Test-Path $modelsTargetCheck)) {
        Remove-Item -Path $modelsTargetCheck -Recurse -Force
    }
    Extract-Single7z $pathModels $VSPluginDir
    $onnxCount = (Get-ChildItem -Path $modelsTargetCheck -Recurse -File -Filter '*.onnx' -ErrorAction SilentlyContinue).Count
    if ($onnxCount -lt 1) {
        throw "MLRT models archive extracted, but no ONNX models were found under $modelsTargetCheck"
    }
    Write-Host "      [OK] $onnxCount .onnx model files installed under $modelsTargetCheck"
} else {
    Write-Host "[6/6] Skipped models (--no-models). vs-mlrt presets will fail until you populate $VSPluginDir\models\."
}

# ---------- Lean trim ----------
# Done BEFORE the smoke test so smoke validates the trimmed install.
# A passing smoke after trim is the real green light: it confirms the
# kept SM resource + ptx fallback + active model dirs are sufficient.
$trimReport = @()
if ($Lean) {
    Write-Host ""
    Write-Host "[lean] Trimming bundle for the local GPU..."

    # Detect compute capability via nvidia-smi. Format: "12.0" -> "sm_120".
    $smTag    = $null
    $gpuName  = ''
    $smiOut   = $null
    try {
        $smiOut = & nvidia-smi --query-gpu=compute_cap,name --format=csv,noheader 2>$null |
                  Select-Object -First 1
    } catch {}
    if ($smiOut) {
        $parts   = $smiOut -split ',', 2
        $cc      = $parts[0].Trim()              # "12.0"
        if ($parts.Count -gt 1) { $gpuName = $parts[1].Trim() }
        $smTag   = 'sm_' + ($cc -replace '\.', '')   # "sm_120"
        Write-Host "      [lean] detected GPU: $gpuName (compute capability $cc -> $smTag)"
    } else {
        Write-Host "      [lean] WARN: nvidia-smi unavailable. Skipping SM-resource trim."
    }

    # Trim other-SM TensorRT builder resources. Keep the matching SM and the
    # ptx fallback; everything else is dead weight on this machine.
    $cudaDir = Join-Path $VSPluginDir 'vsmlrt-cuda'
    if ($smTag -and (Test-Path $cudaDir)) {
        $allBuilders = @(Get-ChildItem -Path $cudaDir -Filter 'nvinfer_builder_resource_sm*_10.dll' -ErrorAction SilentlyContinue)
        $totalRemoved = 0L
        foreach ($f in $allBuilders) {
            $n = $f.Name.ToLower()
            $keep = $n.Contains($smTag.ToLower())
            if (-not $keep) {
                $totalRemoved += $f.Length
                Remove-Item -Path $f.FullName -Force -ErrorAction SilentlyContinue
                $trimReport += "removed $($f.Name) ($([math]::Round($f.Length/1MB,1)) MB)"
            } else {
                Write-Host "      [lean] kept $($f.Name)"
            }
        }
        if ($totalRemoved -gt 0) {
            Write-Host ("      [lean] trimmed other-SM builder resources: {0:N1} MB" -f ($totalRemoved/1MB))
        }
    }

    # Drop unused model packs. We have no preset that uses cugan or
    # waifu2x; dropping their .onnx trees saves ~150 MB and removes ~80
    # files that would otherwise sit unused on disk.
    $modelsBase = Join-Path $VSPluginDir 'models'
    foreach ($unused in @('cugan', 'waifu2x')) {
        $p = Join-Path $modelsBase $unused
        if (Test-Path $p) {
            $sz = (Get-ChildItem -Path $p -Recurse -File -ErrorAction SilentlyContinue |
                   Measure-Object -Property Length -Sum).Sum
            Remove-Item -Path $p -Recurse -Force -ErrorAction SilentlyContinue
            $trimReport += "removed unused models/$unused ($([math]::Round($sz/1MB,1)) MB)"
            Write-Host ("      [lean] removed unused models/{0} ({1:N1} MB)" -f $unused, ($sz/1MB))
        }
    }
}

# ---------- Smoke + marker ----------
Write-Host ""
Write-Host "Smoke: import vsmlrt + check for VSTRT / VSORT namespaces..."
$smoke = @"
import vapoursynth as vs
import vsmlrt
import sys
print('vsmlrt version:', getattr(vsmlrt, '__version__', '(no __version__)'))
core = vs.core
ns = sorted(n for n in dir(core) if not n.startswith('_'))
print('Detected mlrt-related namespaces:')
for n in ns:
    if any(tok in n.lower() for tok in ('rt', 'mlrt', 'ort', 'trt', 'ncnn', 'ov')):
        print('  -', n)
print('Backends in vsmlrt module:', [b for b in dir(vsmlrt.Backend) if not b.startswith('_')] if hasattr(vsmlrt, 'Backend') else 'NO Backend attr')
active = [name for name in ('trt', 'ort', 'ncnn') if hasattr(core, name)]
print('Active inference namespaces:', active)
if not hasattr(vsmlrt, 'Backend') or not active:
    sys.exit(2)
print('MLRT_SMOKE_OK')
"@
$smokeOutput = @(& $VSPython -c $smoke 2>&1)
$smokeExit = $LASTEXITCODE
$smokeOutput | ForEach-Object { Write-Host "      $_" }
if ($smokeExit -ne 0 -or $smokeOutput -notcontains 'MLRT_SMOKE_OK') {
    throw "vsmlrt smoke failed -- no usable VSTRT/VSORT/VSNCNN backend loaded from $VSPluginDir"
}
Write-Host "      [OK] vsmlrt imports and at least one inference backend is active"

# ---------- Drop cache (central Clean-Install-Cache policy) ----------
# Done AFTER smoke passes so we never strand the user with broken state and
# no recovery path. The wipe is intentionally broad for transient install
# artifacts while preserving portable payloads needed for offline repair.
# Implementation defers to Clean-Install-Cache.ps1 so the policy lives in
# one place (preserve list, file patterns).
$cacheReport = @()
if ($DropCache) {
    Write-Host ""
    Write-Host "[cache] Cleaning install cache..."
    $beforeBytes = 0L
    $beforeFiles = @(Get-ChildItem -Path $DLDir -File -ErrorAction SilentlyContinue)
    foreach ($f in $beforeFiles) { $beforeBytes += $f.Length }

    $cleaner = Join-Path $PSScriptRoot 'Clean-Install-Cache.ps1'
    if (Test-Path $cleaner) {
        & $cleaner -ProjectRoot $ProjectRoot
    } else {
        Write-Host "      [cache] WARN: $cleaner missing; falling back to mlrt-only purge"
        foreach ($p in @($pathScripts) + @($trtPaths) + @($pathModels)) {
            if ($p -and (Test-Path $p)) { Remove-Item -Path $p -Force -ErrorAction SilentlyContinue }
        }
    }

    $afterBytes = 0L
    foreach ($f in @(Get-ChildItem -Path $DLDir -File -ErrorAction SilentlyContinue)) {
        $afterBytes += $f.Length
    }
    $freed = [math]::Max([long]0, $beforeBytes - $afterBytes)
    if ($freed -gt 0) {
        $cacheReport += ("freed {0:N1} MB across install cache" -f ($freed/1MB))
        Write-Host ("      [cache] total freed: {0:N1} MB" -f ($freed/1MB))
    }
}

# ---------- Marker ----------
$markerLines = @(
    $MLRTVersion,
    "Bundle=tensorrt",
    "Installed=$(Get-Date -Format o)",
    "NoModels=$NoModels",
    "Lean=$($Lean.IsPresent)",
    "DropCache=$($DropCache.IsPresent)"
)
foreach ($line in $trimReport) { $markerLines += "Trim=$line" }
foreach ($line in $cacheReport) { $markerLines += "Cache=$line" }
Set-Content -Path $Marker -Value ($markerLines -join "`r`n") -Encoding UTF8

Write-Host ""
Write-Host "[SUCCESS] vs-mlrt $MLRTVersion (TensorRT bundle) installed."
Write-Host "          Backend priority in presets: TRT (NVIDIA) -> ORT_DML (any DX12 GPU) -> ORT_CPU"
Write-Host "          First TensorRT engine compile per (model, GPU, resolution) takes 30-120s,"
Write-Host "          then cached -- subsequent runs are immediate."
if ($Lean -or $DropCache) {
    Write-Host ""
    Write-Host "          Lean/full mode is selected by the builder menu or installer switches."
    Write-Host "          On GPU upgrade re-run the MLRT installer; ptx fallback will work meanwhile."
}
Write-Host ""
exit 0
