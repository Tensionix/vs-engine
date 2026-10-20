<#
.SYNOPSIS
  Audion VS Engine - remove the portable VapourSynth of system_core\vapoursynth\

.DESCRIPTION
  The engine is the whole folder: VS-host Python, the VapourSynth core, its
  plugins and vsrepo's package database. Nothing of it lives outside the
  project, so the folder goes to the Recycle Bin and the engine is gone;
  Install-Portable-VapourSynth then Install-VS-Plugins put it back.

  Refuses while a program started from that folder is running (a preset in
  progress): its files are open. Downloads in install\download\ are kept;
  CLEAN INSTALL CACHE removes them.

.PARAMETER ProjectRoot
  Absolute path to project root (where system_core\ lives).
#>
param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'

$VSDir = Join-Path $ProjectRoot 'system_core\vapoursynth'

Write-Host "======================================================================"
Write-Host "  AUDION VS ENGINE - REMOVE PORTABLE VAPOURSYNTH"
Write-Host "======================================================================"
Write-Host "Target VS:    $VSDir"
Write-Host ""

if (-not (Test-Path -LiteralPath $VSDir)) {
    Write-Host "[OK] VapourSynth is not installed: nothing to remove."
    exit 0
}

$marker = Join-Path $VSDir 'portable.vs'
if (Test-Path -LiteralPath $marker) {
    Write-Host "Installed:    $((Get-Content -LiteralPath $marker -TotalCount 1).Trim())"
}

$prefix = (Resolve-Path -LiteralPath $VSDir).Path.TrimEnd('\') + '\'
$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $path = $null
    try { $path = $_.Path } catch { }
    $path -and $path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
})
if ($running.Count -gt 0) {
    Write-Host "[ERROR] Programs of this VapourSynth are running; stop them first:"
    $running | ForEach-Object { Write-Host "        PID $($_.Id)  $($_.Path)" }
    exit 1
}

$bytes = (Get-ChildItem -LiteralPath $VSDir -Recurse -File -Force -ErrorAction SilentlyContinue |
    Measure-Object -Property Length -Sum).Sum
Write-Host ("Size:         {0:N0} MB" -f ($bytes / 1MB))
Write-Host "[1/1] Moving the folder to the Recycle Bin..."
Add-Type -AssemblyName Microsoft.VisualBasic
[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
    $VSDir,
    [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
    [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)
if (Test-Path -LiteralPath $VSDir) { throw "The folder is still there: $VSDir" }

Write-Host ""
Write-Host "[SUCCESS] VapourSynth removed: $VSDir is in the Recycle Bin."
Write-Host ""
exit 0
