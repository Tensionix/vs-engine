# Audion VS Engine - install notes

## The builder

```bat
builder_main.cmd
```

A menu on FZF with fixed numbers:

```text
[01] PYTHON ENV CMD
[02] PYTHON ENV PS
[03] FZF
[09] PORTABLE OFFLINE
[10] VAPOURSYNTH
[11] VS PLUGINS
[12] FFMPEG BTBN AUTO-FALLBACK
[13] FFMPEG GYAN STABLE
[14] REMOVE VAPOURSYNTH
[70] CLEAN INSTALL CACHE
[71] VERIFY / DOCTOR
[90] PROJECT LAUNCHER
[95] OPEN install
[96] OPEN runtime
[97] OPEN wheelhouse
[98] OPEN licenses
[00] EXIT
```

## The Python environment

`[01]` runs `install\Build_Portable_Env_Build.cmd`, the main build; `[02]` runs `install\Build_Portable_Env.cmd`, a thin
wrapper of `Build_Portable_Env.ps1` in the PowerShell 7 of the program (`App\AudionPs.exe`; `pwsh.exe` from `PATH` when
the window is not built yet).

1. Create the folders (`install\init_folders.cmd`).
2. Resolve and download the latest Python Embedded `3.12.x` ZIP.
3. Extract it to `runtime\`; enable `import site` and add the project root (`..`) in the active `python3<minor>._pth`.
4. Download `get-pip.py`, build the local `wheelhouse\` and install the packages: PyYAML, pytest, pip-tools
   (`install\requirements_full.in`).
5. Check that the packages import.

With `runtime\` and `wheelhouse\` already filled, `[09]` (`install\install_portable_offline.cmd`) installs without the
network. The whole program is checked by `[71]` (`install\verify_portable_env.cmd`) once the engine and FFmpeg are in
place: the doctor, the console door, `Start.exe` and the window's own check.

## The engine

The VapourSynth engine is the whole `system_core\vapoursynth\` folder: VS-host Python, the core, its plugins, the vsrepo
package database and, with an NVIDIA RTX card, MLRT. Nothing of it is written outside the project.

- `[10] VAPOURSYNTH` installs the newest stable VapourSynth release (`/R <tag>` names another). VapourSynth R80+ loads
  only API 4 plugins, and the plugin set follows the core.
- `[11] VS PLUGINS`: the plugins are declared in `install\vs_plugins.json` and verified by real Python-module or
  VapourSynth-namespace probes, then by a load of the plugin folder: a plugin the core refuses (an API 3 build, a second
  copy of a namespace) fails the step. PyPI wheels carry most of the stack and are installed with the installed
  `vapoursynth` as a constraint, so `[11]` never moves the core. GitHub release assets carry neo_f3kdb (the newest
  release whose DLL the core loads, a pre-release included) and the `dfttest2.py` wrapper. vsrepo, run through VS-host
  `python.exe`, carries the plugins and VS scripts with no wheel; `mvsfunc` and `nnedi3_resample` are installed with
  dependency resolution disabled because their dependencies are canonical packages of the manifest. BM3D runs on the
  GPU of any vendor through Vulkan (`bm3dvk`), else on the CPU (`bm3d`).
- `[14] REMOVE VAPOURSYNTH` moves `system_core\vapoursynth\` to the Recycle Bin (it refuses while a program started from
  it is running); `[10]` then `[11]` install it again.
- vs-mlrt for the four neural presets - TensorRT, ONNX Runtime and the models - is not a step of the builder: the window
  offers it at its first start and in SETUP only when it finds an NVIDIA RTX card, trimmed to that card
  (`vs_cli.cmd run --operation install_mlrt`; `install\Install-VS-mlrt.cmd /FULL` keeps the whole bundle).
- pip keeps its cache in `install\download\pip\`, vsrepo its package database in `system_core\vapoursynth\vsrepo-data\`.
- Source indexes (L-SMASH `.lwi`, FFMS2 `.ffindex`) are written to `._runtime\index\`, not beside the source.

The same installers stand in the SERVICE menu of the window and behind `vs_cli.cmd run --operation install_vapoursynth`
(`install_vs_plugins`, `install_ffmpeg`, `install_mlrt`, `remove_vapoursynth`). Before downloading, each names its files,
their source and size - `vs_cli.cmd plan --operation install_vapoursynth` says the same without downloading.

## FFmpeg

`[12]` `install\Install-Portable-FFmpeg-BtbN.cmd` downloads the newest BtbN win64 `gpl` release-branch build, never
master or nightly; when BtbN changes its layout or the download fails, it falls back to Gyan. `[13]`
`install\Install-Portable-FFmpeg-Gyan.cmd` downloads the Gyan build. Which version - by the NVIDIA driver:
`install\FFmpeg-Driver-Fallback-Policy.md`. Both write `Tools\ffmpeg\bin\` and reset it first: no stale EXE, DLL or
document survives an upgrade. The GPL builds keep their sources beside them. Downloads are cached in
`install\download\`.

## Cleaning

- `[70]` `install\Clean-Install-Cache.cmd` - the install cache: the transient files of `install\download\` (`get-pip.py`
  and `7z*-extra.7z` stay), the staging folders of the installers, the source index `._runtime\index\`, Python bytecode
  outside `runtime\`, `wheelhouse\`, `App\`, `Tools\` and the user folders, and what a build of the window leaves
  (`Source\bin`, `Source\obj`, `Source\Ps\bin`, `Source\Ps\obj`).
- `cleanup_project.cmd` in the root is a separate tool for a lean source state: it clears `input`, `output`, logs,
  reports, the runtime, the wheelhouse, the engine, FFmpeg, the state of the window and the caches, after a
  confirmation. It is not part of any install flow. A folder to clear that is itself a link (a junction, a symbolic
  link) is refused - what lies there is not the project's; a link inside a folder being cleared is taken away as a link,
  never walked through.

## Rules

- Python Embedded tracks the latest `3.12.x`; no concrete patch version in docs or scripts.
- The bootstrap installs `setuptools`, `wheel` and `packaging` before building or installing the wheels.
- `runtime\`, `wheelhouse\`, `system_core\vapoursynth\`, `system_core\fzf.exe` and `Tools\ffmpeg\` are reproducible
  payloads; an installer replaces only its own.
- GPL and other external tools are explicit install payloads, never bundled silently into the source.
- Licences of a release are collected by Audion Build Licenses from the staged release, not during a build.
