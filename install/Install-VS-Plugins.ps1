<#
.SYNOPSIS
  Installs the canonical VapourSynth plugin stack.

.DESCRIPTION
  VapourSynth R80+ loads only API 4 plugins. The install manifest takes them
  from three places: PyPI wheels (most of the stack), GitHub release assets
  (neo_f3kdb, whose API 4 build is published only there, and the dfttest2
  Python wrapper) and vsrepo (the plugins and VS scripts with no wheel). Every
  item is verified by its Python module or VapourSynth namespace afterwards,
  and the core is checked for plugins it refused to load.

  The core version is chosen by Install-Portable-VapourSynth.ps1 alone: pip
  runs with the installed vapoursynth as a constraint, so a plugin that needs
  a newer core fails here with a message instead of moving the core.

  Nothing is written outside the project: pip keeps its cache in
  install\download\pip, vsrepo its package database in
  system_core\vapoursynth\vsrepo-data. MLRT is intentionally outside this
  installer and remains a separate Full-only payload.
#>
param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [string[]]$Plugins = @()
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

. (Join-Path $PSScriptRoot 'Ensure-7zip.ps1')

$VSDir = Join-Path $ProjectRoot 'system_core\vapoursynth'
$VSPython = Join-Path $VSDir 'python.exe'
$ManifestPath = Join-Path $ProjectRoot 'install\vs_plugins.json'
$DLDir = Join-Path $ProjectRoot 'install\download'

if (-not (Test-Path -LiteralPath $VSPython)) {
    throw "VS-host Python not found at $VSPython. Run Install-Portable-VapourSynth.cmd first."
}
if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Plugin manifest not found: $ManifestPath"
}
if (-not (Test-Path -LiteralPath $DLDir)) { New-Item -Path $DLDir -ItemType Directory -Force | Out-Null }

$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ([int]$manifest.schema_version -ne 2) {
    throw "Unsupported plugin manifest schema: $($manifest.schema_version)"
}

$env:PIP_CACHE_DIR = Join-Path $DLDir 'pip'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

$Headers = @{ 'User-Agent' = 'Audion-VS-Engine' }
# A token lifts the GitHub API limit from 60 requests an hour to 5000.
if ($env:GITHUB_TOKEN) { $Headers['Authorization'] = 'Bearer ' + $env:GITHUB_TOKEN }

function Get-VSHostValue {
    param([Parameter(Mandatory=$true)][string]$Code)
    $value = (& $VSPython -c $Code 2>$null | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($value)) { return '' }
    return $value.Trim()
}

$VSPluginDir = Get-VSHostValue "import vapoursynth; print(vapoursynth.get_plugin_dir())"
if ([string]::IsNullOrWhiteSpace($VSPluginDir)) {
    throw 'Could not resolve the portable VapourSynth plugin directory.'
}
if (-not (Test-Path -LiteralPath $VSPluginDir)) {
    New-Item -Path $VSPluginDir -ItemType Directory -Force | Out-Null
}
$SitePackages = Get-VSHostValue "import sysconfig; print(sysconfig.get_paths()['purelib'])"
$CoreVersion = Get-VSHostValue "import importlib.metadata as m; print(m.version('vapoursynth'))"
if ([string]::IsNullOrWhiteSpace($SitePackages) -or [string]::IsNullOrWhiteSpace($CoreVersion)) {
    throw 'Could not read site-packages or the vapoursynth version of the VS-host Python.'
}

$selected = @{}
foreach ($id in $Plugins) {
    if (-not [string]::IsNullOrWhiteSpace($id)) { $selected[$id.ToLowerInvariant()] = $true }
}
$customSelection = $selected.Count -gt 0

$knownIds = @{}
foreach ($group in @($manifest.python_packages, $manifest.github_assets, $manifest.vsrepo_packages)) {
    foreach ($item in $group) { $knownIds[[string]$item.id.ToLowerInvariant()] = $true }
}
foreach ($id in $selected.Keys) {
    if (-not $knownIds.ContainsKey($id)) { throw "Unknown plugin id in -Plugins: $id" }
}

function Test-Selected {
    param([string]$Id, [switch]$Infrastructure)
    if ($Infrastructure) { return $true }
    if (-not $customSelection) { return $true }
    return $selected.ContainsKey($Id.ToLowerInvariant())
}

function Test-Probe {
    param([Parameter(Mandatory=$true)]$Item)

    if ($Item.probe -eq 'module') {
        $code = "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$($Item.name)') else 1)"
    } elseif ($Item.probe -eq 'namespace') {
        $code = "import vapoursynth as vs,sys; sys.exit(0 if hasattr(vs.core, '$($Item.name)') else 1)"
    } else {
        throw "Unknown probe type '$($Item.probe)' for $($Item.id)"
    }
    & $VSPython -c $code 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

$Constraint = Join-Path $DLDir 'vapoursynth-core.constraint.txt'
[IO.File]::WriteAllText($Constraint, "vapoursynth==$CoreVersion`n", [Text.UTF8Encoding]::new($false))

function Install-PyPIPackage {
    param([Parameter(Mandatory=$true)]$Item)

    Write-Host "      [PYPI] $($Item.package)"
    $pipArguments = @('-m', 'pip', 'install', '--upgrade', '--quiet', '--no-warn-script-location', '--constraint', $Constraint)
    if ($Item.PSObject.Properties['force_reinstall'] -and [bool]$Item.force_reinstall) {
        $pipArguments += '--force-reinstall'
    }
    if ($Item.PSObject.Properties['no_dependencies'] -and [bool]$Item.no_dependencies) {
        $pipArguments += '--no-deps'
    }
    $pipArguments += [string]$Item.package
    & $VSPython @pipArguments 2>&1 |
        ForEach-Object { Write-Host "        $_" }
    if ($LASTEXITCODE -ne 0) { return $false }
    return (Test-Probe -Item $Item)
}

function Get-GitHubReleases {
    # Releases newest first by publication, pre-releases included: neo_f3kdb has its API 4 build only in one. The API
    # does not list them by publication: r11 and r12-beta.1 of neo_f3kdb came out the same day, r11 listed first.
    param([Parameter(Mandatory=$true)][string]$Repo, [int]$Count = 4)
    try {
        $list = @(Invoke-RestMethod -Headers $Headers -Uri "https://api.github.com/repos/$Repo/releases?per_page=10" -TimeoutSec 30 |
            ForEach-Object { $_ } | Where-Object { -not $_.draft } |
            Sort-Object { [datetime]$_.published_at } -Descending | Select-Object -First $Count)
        if ($list.Count -gt 0) {
            return @($list | ForEach-Object {
                [pscustomobject]@{
                    tag    = [string]$_.tag_name
                    assets = @($_.assets | ForEach-Object { [pscustomobject]@{ name = $_.name; url = $_.browser_download_url } })
                }
            })
        }
    } catch {
        Write-Host "      [warn] GitHub API unavailable for $Repo, reading the release pages: $($_.Exception.Message)"
    }
    $html = (Invoke-WebRequest -Headers $Headers -Uri "https://github.com/$Repo/releases" -TimeoutSec 30).Content
    $tags = @([regex]::Matches($html, "/$([regex]::Escape($Repo))/releases/tag/(?<tag>[^`"?#]+)") |
        ForEach-Object { [uri]::UnescapeDataString($_.Groups['tag'].Value) } | Select-Object -Unique | Select-Object -First $Count)
    if ($tags.Count -eq 0) { throw "No release found on https://github.com/$Repo/releases" }
    return @($tags | ForEach-Object {
        $tag = $_
        $assetsHtml = (Invoke-WebRequest -Headers $Headers -TimeoutSec 30 `
            -Uri "https://github.com/$Repo/releases/expanded_assets/$([uri]::EscapeDataString($tag))").Content
        $assets = @(
            [regex]::Matches($assetsHtml, 'href="(?<href>/[^"]+/releases/download/[^"]+)"') | ForEach-Object {
                $href = $_.Groups['href'].Value
                [pscustomobject]@{ name = [uri]::UnescapeDataString((Split-Path $href -Leaf)); url = "https://github.com$href" }
            }
        )
        [pscustomobject]@{ tag = $tag; assets = $assets }
    })
}

function Install-GitHubAsset {
    # The newest release whose file the core loads: a release with an API 3 build is passed over for the one before.
    param([Parameter(Mandatory=$true)]$Item)

    $targetDir = if ($Item.target -eq 'plugins') { $VSPluginDir } elseif ($Item.target -eq 'site-packages') { $SitePackages } else {
        throw "Unknown target '$($Item.target)' for $($Item.id)"
    }
    foreach ($release in Get-GitHubReleases -Repo ([string]$Item.repo)) {
        $asset = @($release.assets | Where-Object { $_.name -match [string]$Item.asset } | Select-Object -First 1)
        if ($asset.Count -eq 0) {
            Write-Host "      [skip] $($Item.repo) $($release.tag): no asset matching $($Item.asset)"
            continue
        }
        $asset = $asset[0]
        Write-Host "      [GITHUB] $($Item.repo) $($release.tag): $($asset.name)"
        $download = Join-Path $DLDir $asset.name
        Invoke-WebRequest -Headers $Headers -Uri $asset.url -OutFile $download -TimeoutSec 300
        if ($Item.PSObject.Properties['member'] -and -not [string]::IsNullOrWhiteSpace([string]$Item.member)) {
            $staging = Join-Path $DLDir "$($Item.id)-$($release.tag)"
            if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
            Expand-7zArchive -Archive $download -Destination $staging -ProjectRoot $ProjectRoot
            $member = Join-Path $staging ([string]$Item.member).Replace('/', '\')
            if (-not (Test-Path -LiteralPath $member)) {
                Write-Host "      [skip] $($asset.name) has no $($Item.member)"
                Remove-Item -LiteralPath $staging -Recurse -Force
                continue
            }
            $placed = Join-Path $targetDir (Split-Path $member -Leaf)
            Copy-Item -LiteralPath $member -Destination $placed -Force
            Remove-Item -LiteralPath $staging -Recurse -Force
        } else {
            $placed = Join-Path $targetDir $asset.name
            Copy-Item -LiteralPath $download -Destination $placed -Force
        }
        if (Test-Probe -Item $Item) { return $true }
        Write-Host "      [skip] $($release.tag): the core does not load it ($($Item.probe) '$($Item.name)' missing)"
        Remove-Item -LiteralPath $placed -Force
    }
    return $false
}

function Test-VsrepoOutput {
    param([object[]]$Output)
    return -not [bool]($Output | Where-Object {
        $_ -match '(?i)failed to download|failed to decompress|packages? failed'
    })
}

Write-Host '======================================================================'
Write-Host '  AUDION VAPOURSYNTH - CANONICAL PLUGIN INSTALLER'
Write-Host '======================================================================'
Write-Host "VS Python:   $VSPython"
Write-Host "VS core:     R$CoreVersion"
Write-Host "Plugin dir:  $VSPluginDir"
Write-Host "Manifest:    $ManifestPath"
Write-Host ''

$ok = [System.Collections.Generic.List[string]]::new()
$failed = [System.Collections.Generic.List[string]]::new()

# Plugins of the API 3 stack this installer used to take from vsrepo, and wheels that duplicate a namespace of the
# manifest: a second build of a namespace is refused by the core, and which one wins depends on the load order.
Write-Host '[1/6] Removing retired and duplicate packages...'
$installedNames = @(& $VSPython -m pip list --format=freeze 2>$null | ForEach-Object { ($_ -split '==')[0].ToLowerInvariant() })
foreach ($packageName in @($manifest.remove_python_packages)) {
    if ($installedNames -notcontains ([string]$packageName).ToLowerInvariant()) { continue }
    Write-Host "      [REMOVE] $packageName"
    & $VSPython -m pip uninstall --yes --quiet $packageName 2>&1 |
        ForEach-Object { Write-Host "        $_" }
}
Write-Host '      [OK] Retired packages are gone.'

Write-Host '[2/6] Installing PyPI packages...'
foreach ($item in $manifest.python_packages) {
    $infrastructure = $item.id -in @('vsrepo', 'vsutil')
    if (-not (Test-Selected -Id $item.id -Infrastructure:$infrastructure)) { continue }
    if (Install-PyPIPackage -Item $item) {
        $ok.Add([string]$item.id)
        Write-Host "      [OK] $($item.id)"
    } else {
        $failed.Add([string]$item.id)
        Write-Host "      [FAIL] $($item.id)"
    }
}
if ($failed.Count -gt 0) { throw "Required PyPI package installation failed: $($failed -join ', ')" }

Write-Host '[3/6] Installing GitHub release assets...'
foreach ($item in $manifest.github_assets) {
    if (-not (Test-Selected -Id $item.id)) { continue }
    $installed = $false
    try {
        $installed = Install-GitHubAsset -Item $item
    } catch {
        Write-Host "      [FAIL] $($item.id): $($_.Exception.Message)"
    }
    if ($installed) {
        $ok.Add([string]$item.id)
        Write-Host "      [OK] $($item.id)"
    } else {
        $failed.Add([string]$item.id)
    }
}

$VSRepoPy = Get-VSHostValue "import pathlib,vsrepo; print(pathlib.Path(vsrepo.__file__).with_name('vsrepo.py'))"
if ([string]::IsNullOrWhiteSpace($VSRepoPy) -or -not (Test-Path -LiteralPath $VSRepoPy)) {
    throw 'vsrepo.py was not found in VS-host site-packages.'
}

# vsrepo unpacks .7z archives (FFMS2) with a 7z.exe beside vsrepo.py, else with a system 7-Zip. The project's own
# 7za.exe is put there, so a machine without 7-Zip installs the same set.
$vsrepo7z = Join-Path (Split-Path $VSRepoPy -Parent) '7z.exe'
if (-not (Test-Path -LiteralPath $vsrepo7z)) {
    Copy-Item -LiteralPath (Ensure-7za -ProjectRoot $ProjectRoot) -Destination $vsrepo7z -Force
}

# vsrepo downloads plugin binaries from GitHub anonymously, and 60 requests an hour is not enough for this manifest.
# The wrapper hands it the token from outside, retries downloads, keeps vsrepo's package database inside the VS-host
# and builds that database from GitHub when www.vapoursynth.com does not give it.
$VSRepoAuth = Join-Path $PSScriptRoot 'vsrepo_github_auth.py'
if (-not (Test-Path -LiteralPath $VSRepoAuth)) {
    throw "vsrepo_github_auth.py is missing beside this script: $VSRepoAuth"
}

Write-Host '[4/6] Refreshing the vsrepo package database...'
Push-Location $VSDir
try {
    $updated = $false
    for ($attempt = 1; $attempt -le 3 -and -not $updated; $attempt++) {
        & $VSPython $VSRepoAuth $VSRepoPy update
        $updated = $LASTEXITCODE -eq 0
        if (-not $updated -and $attempt -lt 3) {
            Write-Host "      [RETRY $attempt/3] vsrepo database update failed; waiting before retry."
            Start-Sleep -Seconds (3 * $attempt)
        }
    }
    if (-not $updated) { throw 'vsrepo update failed after 3 attempts.' }
} finally {
    Pop-Location
}
Write-Host '      [OK] Package database refreshed.'

Write-Host '[5/6] Installing native plugins and VS scripts through vsrepo...'
Push-Location $VSDir
try {
    foreach ($item in $manifest.vsrepo_packages) {
        if (-not (Test-Selected -Id $item.id)) { continue }
        $arguments = @($VSRepoAuth, $VSRepoPy, 'install', [string]$item.id)
        if ($item.PSObject.Properties['skip_dependencies'] -and [bool]$item.skip_dependencies) {
            $arguments += '-d'
            Write-Host "      [VSREPO] $($item.id) (dependency resolution disabled; dependencies are canonical packages)"
        } else {
            Write-Host "      [VSREPO] $($item.id)"
        }
        $installed = $false
        for ($attempt = 1; $attempt -le 3 -and -not $installed; $attempt++) {
            $output = @(& $VSPython @arguments 2>&1)
            $exitCode = $LASTEXITCODE
            $output | ForEach-Object { Write-Host "        $_" }
            $installed = $exitCode -eq 0 -and (Test-VsrepoOutput -Output $output)
            if (-not $installed -and $attempt -lt 3) {
                Write-Host "        [RETRY $attempt/3] $($item.id) failed; waiting before retry."
                Start-Sleep -Seconds (3 * $attempt)
            }
        }
        if ($installed) {
            $ok.Add([string]$item.id)
        } else {
            $failed.Add([string]$item.id)
        }
    }
} finally {
    Pop-Location
}

Write-Host '[6/6] Verifying imports, VapourSynth namespaces and the plugin load...'
$allItems = @($manifest.python_packages) + @($manifest.github_assets) + @($manifest.vsrepo_packages)
foreach ($item in $allItems) {
    $infrastructure = $item.id -in @('vsrepo', 'vsutil')
    if (-not (Test-Selected -Id $item.id -Infrastructure:$infrastructure)) { continue }
    if (Test-Probe -Item $item) {
        Write-Host "      [OK] $($item.id): $($item.probe) '$($item.name)'"
    } else {
        if (-not $failed.Contains([string]$item.id)) { $failed.Add([string]$item.id) }
        Write-Host "      [FAIL] $($item.id): missing $($item.probe) '$($item.name)'"
    }
}

# The core says why it did not load a plugin - an API 3 build, a second copy of a namespace - in its log, while it
# loads them: a handler set on the core afterwards sees nothing, so vspipe, which prints the log, reads a blank clip.
$loadScript = Join-Path $DLDir 'plugin-load-check.vpy'
[IO.File]::WriteAllText($loadScript, "import vapoursynth as vs`nvs.core.std.BlankClip(length=1).set_output()`n", [Text.UTF8Encoding]::new($false))
$VSPipe = Join-Path $VSDir 'Scripts\vspipe.exe'
$loadOutput = @(& $VSPipe --info $loadScript - 2>&1 | ForEach-Object { "$_" })
$refused = @($loadOutput | Where-Object { $_ -match '(?i)api ?3|no longer supported|already loaded|failed to load|could not load' })
if ($refused.Count -gt 0) {
    $failed.Add('plugin_load')
    Write-Host '      [FAIL] The core refused plugins:'
    $refused | ForEach-Object { Write-Host "        $_" }
} else {
    $ok.Add('plugin_load')
    Write-Host '      [OK] The core loaded every plugin of the plugin folder.'
}
Remove-Item -LiteralPath $loadScript -Force -ErrorAction SilentlyContinue

if ($Plugins.Count -eq 0) {
    Write-Host '      [SMOKE] Rendering synthetic QTGMC and NNEDI3 frames...'
    # QTGMC as the presets call it: audion_lib.havsfunc() runs it with zsmooth where focus2 (API 3) does not load.
    $smokeCode = @'
import vapoursynth as vs
import audion_lib
import nnedi3_resample

havsfunc = audion_lib.havsfunc()
core = vs.core
clip = core.std.BlankClip(width=640, height=480, format=vs.YUV420P8, length=2, fpsnum=25)
qtgmc = havsfunc.QTGMC(clip, Preset="Ultra Fast", TFF=True)
qtgmc.get_frame(0)
resized = nnedi3_resample.nnedi3_resample(clip, target_width=320, target_height=240)
resized.get_frame(0)
print("QTGMC_FRAME_OK")
print("NNEDI3_RESAMPLE_FRAME_OK")
'@
    $smokeOutput = @($smokeCode | & $VSPython - 2>&1)
    $smokeExitCode = $LASTEXITCODE
    $smokeOutput | ForEach-Object { Write-Host "        $_" }
    if ($smokeExitCode -eq 0 -and $smokeOutput -contains 'QTGMC_FRAME_OK' -and $smokeOutput -contains 'NNEDI3_RESAMPLE_FRAME_OK') {
        $ok.Add('runtime_smoke')
        Write-Host '      [OK] Synthetic restoration frames rendered.'
    } else {
        $failed.Add('runtime_smoke')
        Write-Host '      [FAIL] Synthetic restoration frame smoke failed.'
    }
}

Write-Host ''
Write-Host '======================================================================'
Write-Host "  VERIFIED: $($ok.Count) install action(s)"
if ($failed.Count -gt 0) {
    $uniqueFailed = @($failed | Select-Object -Unique)
    Write-Host "  FAILED:   $($uniqueFailed -join ', ')"
    Write-Host '======================================================================'
    exit 2
}
Write-Host '  BASE PLUGIN STACK: READY'
Write-Host '  MLRT: separate Full-only install stage'
Write-Host '======================================================================'
exit 0
