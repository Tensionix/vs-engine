---
name: audion-vs-engine
description: Process video with Audion VS Engine - VapourSynth presets of four palettes run on a file or a whole folder and encoded by FFmpeg - denoise (DFTTest, BM3D on any GPU through Vulkan or on the CPU, the strength by the noise measured in the source), deband, controlled grain, film looks (Kodak 35 mm stocks, 16 mm, Super 8, IMAX 70 mm, bleach bypass, anamorphic flares), retro (VHS and CRT, a 90s camcorder, Polaroid), restoration (QTGMC deinterlace, TIVTC inverse telecine, MVTools denoise, deblock, derainbow, dehaze, NNEDI3 2x) and, with an NVIDIA RTX card, the neural presets on vs-mlrt (DPIR denoise, Real-ESRGAN 2x, Soft HD rebuild 2x); render the middle frame of a video before and after a preset to compare looks; save a preset with its values as a profile and run it; install and check the engine. Run everything through the console command vs_cli.cmd and read its outcome. Use when asked to denoise, deband, add or restore film grain, give a video a film, retro or analogue look, deinterlace, remove telecine, clean compression blocks, rainbows or haze, upscale, interpolate frames, compare a look on a frame, run a VapourSynth preset or profile on footage, install VapourSynth, its plugins, FFmpeg or MLRT, or to change and check the program itself.
---

# Audion VS Engine

A portable program for picture work by VapourSynth and FFmpeg. `Start.exe` opens the window (`App\AudionVSEngine.exe`,
C# on Avalonia); every button of the window is an operation of the console command `vs_cli.cmd` (Python 3.12 of
`runtime\`, the engine in `system_core\`), and the window runs nothing the command cannot. A preset is a `.vpy` script of
`system_core\presets\<palette>\`; the engine runs `vspipe | ffmpeg` with the values of its fields. VapourSynth with its
plugins lives in `system_core\vapoursynth\` (installed by the program, not shipped), FFmpeg in `Tools\ffmpeg\bin\`.

Paths below are relative to the project root. Sibling projects are resolved from the parent folder; never hardcode the
drive. Why things are as they are is in `MEMORY.md`; the rules of the workshop are in `CLAUDE.md`. The person's guide is
`docs\USER_GUIDE_RU.md` / `_EN.md`, the command line `docs\CLI_RU.md` / `_EN.md`, every preset in words
`docs\tools\VapourWiki_EN.md`. Every operation with every field, choice and range is in `docs\OPERATIONS_EN.md`, made
from the data of the program (`vs_cli.cmd map --docs`).

## The folders

| Folder | What it holds |
|---|---|
| `input\` | the Source by default: every video of the folder and its subfolders, or one file named by `--source` |
| `output\` | the Target by default: `<Palette>\<preset>_<encoder>\<the folders of the Source>\<name>.<ext>` - `Precision\`, `Film Looks\`, `Retro\`, `Restoration\`; a profile - `Profiles\<profile>_<encoder>\` |
| `logs\` | the journal of every run, `<time>_<operation>.log` |
| `report\` | `<time>_<operation>\run_report.json` and `.md`, a JSON of every file beside them |
| `config\` | `tool_manifest.yaml` - the operations, their fields and texts; `window_layout.yaml` - where each stands in the window; `profiles\*.json`; the state of the window (settings, path history, caches) |
| `system_core\presets\` | the presets, `<palette>\<id>.vpy`, and `audion_lib.py` - what they share (the loader, BM3D, DFTTest, grain, the noise measure) |
| `system_core\vapoursynth\` | the engine: its own Python, VapourSynth, the plugins, MLRT; `.audion-mlrt.marker` - MLRT installed |
| `install\` | the installers, `vs_plugins.json` (the set of plugins), `Build-App.cmd`, `Bench-AllPresets.ps1` |
| `cli\`, `launcher_project*.cmd`, `launcher_tools.cmd`, `builder_main.cmd` | the console menus on FZF over `vs_cli.cmd` |
| `Source\` | the window (C#); `install\Build-App.cmd` builds it into `App\` |
| `._runtime\` | scratch: `index\` (the indexes of the sources, never beside the person's file), `frame\`, `session\` |

## The console command

```
vs_cli.cmd describe                                     the program, the operations, their fields, the layout, the machine (JSON)
vs_cli.cmd run --operation ID [--set NAME=VALUE ...]    an operation: a preset, a profile, a service
vs_cli.cmd run ... --source FILE_OR_FOLDER --target FOLDER --result OUTCOME.json
vs_cli.cmd run ... --encoder h264_crf14                 an encoder of `list encoders` put on the cards
vs_cli.cmd run ... --dry-run                            the commands of vspipe and FFmpeg for every file, nothing run
vs_cli.cmd frame --operation ID --source FILE [--at 0.5] [--out FOLDER] [--set ...]   one frame before and after, as PNG
vs_cli.cmd list presets|encoders|profiles|paths         lines to read
vs_cli.cmd map [--out MAP.json] [--docs]                the map of the program; --docs writes the reference documents
vs_cli.cmd components [--latest|--refresh]              VapourSynth, the plugins, MLRT, FFmpeg, the GPU driver
vs_cli.cmd plan --operation install_vapoursynth         what an installer would download: files, source, size
vs_cli.cmd form                                         the form server of the window (a JSON request a line in, an answer out)
vs_cli.cmd version
```

Exit codes: `0` done, `1` a file failed, `2` a wrong call or a run refused before it began (nothing was run), `130`
stopped. A wrong call is a field the operation has not, a number outside its range, a value that is none of its choices,
`--dry-run` of an operation that cannot only say its commands. A refused run is one its preflight stopped - no engine, no
video in the Source, a neural preset without MLRT; its `[PREFLIGHT] FAIL` lines say why.

- `--set NAME=VALUE` sets a field; `--params FILE` - the fields as a JSON object (a text with quotes, like
  `profile_values`, goes this way: PowerShell breaks JSON quotes on the way into a `.cmd`). Unnamed fields keep their
  defaults. `--encoder NAME` puts a named encoder on the cards; a `--set` of a card is laid over it.
- The machine fields are on every preset: `vs_accel` (auto | cpu | gpu - where BM3D or the neural network runs; it moves
  something only on `shadow_denoise_sota`, `filmic_rebuild` and the neural presets), the cards of the encoder
  (`encode_family` x264 | x265 | prores | dnxhr, `encode_backend` cpu | nvenc | qsv | amf, `encode_quality` 14 | 17 | 21,
  `encode_container` mp4 | mkv, `prores_profile`, `prores_wrapper` mov | mxf, `dnxhr_profile`) and `overwrite`. A hardware
  encoder this machine has not passed (`hardware_capabilities`) becomes the CPU with a `[NOTE]` line.
- `--result FILE` - the outcome as JSON, written whatever it is: `operation`, `outcome` (`done`, `failed`, `refused`,
  `stopped`), `ok`, `message`, `processed`, `skipped`, `failed`, `parameters`, `seconds`, `log_file`, `source`, `target`
  and `data` (the files with their outcome, the encoder, the output folder, the measured noise). Read it rather than the
  journal. A `.json` outside the Source; a full path, or call from the program folder.
- `--cancel-file FILE` stops the run when the file appears: vspipe and FFmpeg end, the half-written file goes. `--only
  mov,mxf` narrows the kinds of file. `--live` turns the frame bar into service lines (the window uses it).
- The journal: `[PREFLIGHT]`, `[RUN]`, `[FILE] 2/5 name`, `[PROGRESS] name [###---] 42% 13/25 2.24 fps ETA 00:05` with
  `Frame: N/M (fps)`, `[NOISE] preset: noise Y / U / V -> what it made of it`, `[SKIP]`, `[OK]`, `[FAIL]`, `[DONE] n done,
  n passed over, n failed`, `[DRY RUN]`, `[STOPPED]`, `[REFUSED]`, `[NOTE]`. A caller by a pipe gets `::vs::{...}`
  (`started`, `progress`, `activity`, `finished`) too; a console does not.
- A result is written as `<name>.writing-<pid>-<token>.<ext>` and renamed when whole; a result already there is passed
  over (`[SKIP]`) unless `--set overwrite=true` - a second run into the same Target reads `done` with `processed` 0.
- `frame` prints one line of JSON: `before` and `after` (`path`, `frame`, `frames`, `width`, `height`, `fps`), `seconds`,
  `params`, `noise`; `ok: false` and `error` when it cannot. The same `.vpy` and values as a run; nothing goes into the
  Target. `--at` is a share of the length (0.5 - the middle); `--side before|after|both`; `--max-width 1920` (0 - as it is).

## Sections, groups and presets

The ribbon of the window - a palette, the group of the kind of processing, the preset - with the call that does the same:

<!-- map:sections -->
| Section | Group | Preset | Call |
|---|---|---|---|
| PRECISION | Denoise | Mild Denoise | `vs_cli.cmd run --operation mild_denoise` |
| PRECISION | Denoise | Shadow Denoise SOTA | `vs_cli.cmd run --operation shadow_denoise_sota` |
| PRECISION | Denoise | Chroma Cleanup | `vs_cli.cmd run --operation chroma_cleanup` |
| PRECISION | Deband | Deband Safe | `vs_cli.cmd run --operation deband_safe` |
| PRECISION | Deband | Deband Fine Grain | `vs_cli.cmd run --operation deband_fine_grain` |
| PRECISION | Master | Filmic Rebuild | `vs_cli.cmd run --operation filmic_rebuild` |
| PRECISION | Master | Archive Clean | `vs_cli.cmd run --operation archive_clean` |
| PRECISION | Master | Pregrade Prep | `vs_cli.cmd run --operation pregrade_prep` |
| FILM LOOKS | Film stock | Film 35mm | `vs_cli.cmd run --operation film_35mm` |
| FILM LOOKS | Film stock | Film 16mm | `vs_cli.cmd run --operation film_16mm` |
| FILM LOOKS | Film stock | Super 8 | `vs_cli.cmd run --operation super8` |
| FILM LOOKS | Film stock | IMAX 70mm | `vs_cli.cmd run --operation imax_70mm` |
| FILM LOOKS | Look | Cinematic | `vs_cli.cmd run --operation cinematic` |
| FILM LOOKS | Look | Bleach Bypass | `vs_cli.cmd run --operation bleach_bypass` |
| FILM LOOKS | Look | Anamorphic Scope | `vs_cli.cmd run --operation anamorphic_scope` |
| RETRO | Video | VHS CRT | `vs_cli.cmd run --operation vhs_crt` |
| RETRO | Video | Camcorder 90s | `vs_cli.cmd run --operation camcorder_90s` |
| RETRO | Photo | Polaroid | `vs_cli.cmd run --operation polaroid` |
| RESTORATION | Interlace | QTGMC Deinterlace | `vs_cli.cmd run --operation qtgmc_deinterlace` |
| RESTORATION | Interlace | TIVTC IVTC | `vs_cli.cmd run --operation tivtc_ivtc` |
| RESTORATION | Noise | MVTools MCDegrain | `vs_cli.cmd run --operation mvtools_mcdegrain` |
| RESTORATION | Noise | DPIR Denoise ¹ | `vs_cli.cmd run --operation dpir_denoise` |
| RESTORATION | Artefacts | Deblock H.264 Artefacts | `vs_cli.cmd run --operation deblock_h264_artefacts` |
| RESTORATION | Artefacts | Derainbow Decross | `vs_cli.cmd run --operation derainbow_decross` |
| RESTORATION | Artefacts | Dehaze Local Contrast | `vs_cli.cmd run --operation dehaze_local_contrast` |
| RESTORATION | Scale | NNEDI3 Upscale 2X | `vs_cli.cmd run --operation nnedi3_upscale_2x` |
| RESTORATION | Scale | Real-ESRGAN 2x ¹ | `vs_cli.cmd run --operation vsmlrt_realesrgan_2x` |
| RESTORATION | Scale | Soft HD Rebuild 2x ¹ | `vs_cli.cmd run --operation soft_hd_rebuild_2x` |
| PROFILES |  | Run a profile | `vs_cli.cmd run --operation profile_run` |

¹ on vs-mlrt: shown with an NVIDIA RTX card or MLRT.
<!-- /map -->

SETUP - the additional components the program works with; at the start the window asks to install the ones not yet
here:

<!-- map:setup -->
| Operation | What it is | Call |
|---|---|---|
| Install VapourSynth | The newest stable portable VapourSynth into system_core\vapoursynth (step 10 of the builder). | `vs_cli.cmd run --operation install_vapoursynth` |
| Install the plugins | The plugins of install\vs_plugins.json into VapourSynth (step 11 of the builder); the core is not moved. | `vs_cli.cmd run --operation install_vs_plugins` |
| Install FFmpeg | FFmpeg of Gyan into Tools\ffmpeg by the NVIDIA driver: the newest stable, 9.0.2 at least, without an NVIDIA card and from the LTS driver 610.88; below it 8.0.1 (570-610.87) or 7.1 so that NVENC works, and not every operation is possible (step 13 of the builder). | `vs_cli.cmd run --operation install_ffmpeg` |
| Install MLRT | vs-mlrt - TensorRT, ONNX Runtime and the models - into VapourSynth, trimmed to this video card: the neural presets DPIR, Real-ESRGAN and Soft HD Rebuild. Offered at the first start and in SETUP when an NVIDIA RTX card is found; the builder does not install it. | `vs_cli.cmd run --operation install_mlrt` |
| Remove VapourSynth | The folder of the engine, system_core\vapoursynth, with its plugins and MLRT, goes to the Recycle Bin (step 14 of the builder). | `vs_cli.cmd run --operation remove_vapoursynth` |
<!-- /map -->

SERVICE, DETAILS and the buttons of a page:

<!-- map:service -->
| Operation | What it is | Call |
|---|---|---|
| Doctor | Checks the whole engine: the two Pythons, VapourSynth, every plugin, FFmpeg, BM3D on the video card. | `vs_cli.cmd run --operation doctor` |
| File list | The videos of the Source the next run takes, with their folders. | `vs_cli.cmd run --operation source_list` |
| Hardware capabilities | Short FFmpeg encodes with NVENC, QuickSync and AMF: which hardware encoders work on this machine. | `vs_cli.cmd run --operation hardware_capabilities` |
| Check every preset | Every preset on a test clip, a frame each: what runs on this machine and how fast. | `vs_cli.cmd run --operation bench_presets` |
| BM3D: video card or CPU | BM3D through Vulkan (bm3dvk) against BM3D on the CPU (bm3d) on the first video of the Source: frames a second of each. | `vs_cli.cmd run --operation bench_gpu` |
| Source info | What ffprobe knows of every video of the Source: size, frame rate, length, codec, range, colour. | `vs_cli.cmd run --operation probe_source` |
| Save a profile | The settings of a preset and the encoder of the cards saved as a profile in config\profiles. | `vs_cli.cmd run --operation profile_save` |
<!-- /map -->

Which preset for which material, in short (all of them in words: `docs\tools\VapourWiki_EN.md`):

| Material | Preset |
|---|---|
| noise in the shadows of a dark digital shot | `shadow_denoise_sota` (BM3D held to the shadows) |
| uniform noise, any machine | `mild_denoise` (DFTTest on the CPU) |
| colour noise only | `chroma_cleanup` |
| heavy noise, high ISO, keep the texture | `mvtools_mcdegrain`; with MLRT - `dpir_denoise` |
| banding in skies and walls | `deband_safe`, `deband_fine_grain` (puts a fine texture back) |
| one preset for film-like material | `filmic_rebuild` (BM3D, deband, grain by brightness) |
| a neutral master for the archive / minimum before Resolve | `archive_clean` / `pregrade_prep` |
| a film look | `cinematic`, `film_35mm --set stock=250D|500T|50D`, `film_16mm`, `super8`, `imax_70mm`, `bleach_bypass`, `anamorphic_scope` |
| retro | `vhs_crt`, `camcorder_90s`, `polaroid` |
| interlaced DV, HDV, broadcast | `qtgmc_deinterlace` |
| 29.97 with 3:2 pulldown | `tivtc_ivtc` (refuses a source under 29 fps) |
| over-compressed H.264 / MPEG, rainbows, haze | `deblock_h264_artefacts`, `derainbow_decross`, `dehaze_local_contrast` |
| twice the size | `nnedi3_upscale_2x`; with MLRT - `vsmlrt_realesrgan_2x`, `soft_hd_rebuild_2x` |
| more frames, smooth motion | none: RIFE is out until it runs right on the video card - tell the person so |

The seven denoise presets measure the noise of the source (`noise=auto`, the default): their settings are made for about
2 codes of noise and grow with more, never go lower; `noise=fixed` takes the settings as they are. The neural presets
(`needs: mlrt` in the manifest) are shown and run only with MLRT; `describe` → `machine` says `rtx` (the card nvidia-smi
names), `mlrt` (the release installed) and `neural` (shown). `AUDION_VS_RTX=<a card name>` names a card for a check on a
machine without one, `AUDION_VS_RTX=0` hides one.

## The window and its controls

The window is driven without a mouse by UI Automation (`Source\Tools\release-walk.ps1` shows how): every control below
has its AutomationId. Never move the real pointer; find the window by the id of its process.

| Where | Control | AutomationId | What it runs |
|---|---|---|---|
| header | SERVICE and its menu | `service`, `run_<operation>` | the checks of `service` of the layout |
| header | SETUP and its sheet | `setup`; the dot `setup_missing`; `update_<component>`, `setup_install_missing`, `run_remove_vapoursynth`, `components_refresh` | the components of `setup` of the layout (MLRT only with an RTX card): install, update, INSTALL ALL, remove the engine |
| a window of its own | Install additional components | `setup_item_<component>`, `setup_install`; at the start `setup_later`, `setup_hint`, `setup_close`, `setup_open` (OPEN SETUP - the sheet SETUP); from SETUP `setup_cancel` | asked at every start while a component is not installed |
| header | the badges of the engine | `component_<id>` | `components`: VapourSynth, plugins N of M, MLRT, FFmpeg, the GPU |
| header | RU / EN, the theme, SETTINGS, ABOUT | `LangRu`, `LangEn`, `ThemeButton`, `SheetSettings`, `SheetAbout` | the look of the window, `config\window_settings.json` |
| ribbon | a palette | `section_<palette>` | - |
| ribbon | a preset in its group | `page_<palette>_<preset>` | opens the page of the preset |
| page | RUN | `run_<preset>` | `run --operation <preset>` with the values of the page |
| page | COMMAND | `dry_<preset>` | the same with `--dry-run` |
| page | SAVE A PROFILE | `own_profile_save` | asks the name (`ask_value`, `AskYes`), runs `profile_save` |
| page | back to the defaults | `ActionReset` | the form of the page as it opens |
| form | a choice / a switch of it | `field_<field>_<value>` | `set` of the form server |
| form | a number and its slider | `field_<field>`, `slide_<field>` | the box takes a typed value; the slider a step |
| form | a flag | `field_<field>` | - |
| form | a card of the encoder | `field_encode_family_<family>` | chooses the card; its fields inside it |
| preview | before / after / side by side | `preview_before`, `preview_after`, `preview_both` | the middle frame of a video of the Source (`frame`) |
| preview | the videos of the Source | `preview_back`, `preview_next`, `preview_count`, `preview_name` | steps through the queue |
| preview | again, fold, the state, the facts | `preview_again`, `preview_fold`, `preview_state`, `preview_facts` | counted by itself 1.2 s after the last change |
| engine card | install | `engine_install_vapoursynth`, `engine_install_vs_plugins`, `engine_install_ffmpeg`, `engine_install_mlrt` | the installer, its plan beside it |
| paths | Source, Target | `route_source`, `route_target` | a path typed; an empty field - `input\` / `output\` |
| paths | pick, add a file, history, pin, open | `route_pick_source`, `route_pick_file`, `route_history_source`, `route_pin_source`, `route_open_source` (and `_target`) | `config\path_history.json` |
| paths | RESET, LIST, DETAILS | `route_reset`, `route_list`, `route_details` | both paths back to the folders of the program; `source_list`; `probe_source` |
| paths | TO SOURCE, CLEAR | `route_to_source`; `route_clear` → `clear_source`, `clear_target`, `clear_both` | the result moved into the emptied Source; contents to the Recycle Bin, asked first |
| journal | LOGS, REPORT, CONFIG, copy, clear, wide | `LogsButton`, `ReportButton`, `ConfigButton`, `CopyLogButton`, `ClearLogButton`, `WideLogButton` | - |
| journal | the live line, STOP | `ActivityText`, `stop` | the frame bar of a run; the cancel file, a second press ends at once |
| command line | PS / CMD, the box, history, file, folder, run | `command_shell_ps`, `command_shell_cmd`, `command_box`, `command_history`, `command_file`, `command_folder`, `command_run` | a command of `App\AudionPs.exe` or cmd.exe into the journal |
| state | the status line | `StatusText` | `Готово: <name>` / `Done: <name>`, `Остановлено`, `отказ до начала`, `ошибка` |

## Procedures

### Process a file or a folder

1. Find the material: in `input\`, or a path the person gives - pass it with `--source`. Never move, change or clear the
   person's file or `input\`.
2. `vs_cli.cmd run --operation probe_source --source FILE_OR_FOLDER` - size, frame rate, length, codec, range, colour of
   every video. Camera RAW - ProRes RAW, ARRIRAW, Sony RAW / X-OCN, R3D, N-RAW, BRAW, Canon Cinema RAW - the engine
   does not read (`[PREFLIGHT] FAIL camera RAW`, or `[FAIL]` of that file among others; `core\camera_raw.py`, the table
   `config\camera_raw.yaml`): the line names the program that opens it and its page - ask the person to convert it
   there into ProRes 4444 or DNxHR 444; never convert it with FFmpeg by yourself - its colours come out raw.
3. Choose the preset by the table above; `vs_cli.cmd describe` gives every field, `docs\OPERATIONS_EN.md` the same in words.
4. Look before running: `vs_cli.cmd frame --operation ID --source FILE --out <scratch folder> [--set ...]`, then look at
   `before.png` and `after.png` (a denoise is judged at 100 %: `--max-width 0`).
5. `vs_cli.cmd run --operation ID [--set ...] [--encoder NAME] --source ... --target ... --result outcome.json`.
6. Read `outcome.json`: `outcome` `done`, `processed` > 0. The file is under
   `<Target>\<Palette>\<preset>_<encoder>\`; check it with `Tools\ffmpeg\bin\ffprobe.exe -v error -show_streams -show_format FILE`
   against the source (size, rate, length; twice the size for the 2x presets).

### Choose a look by eye

`frame` of each candidate on the same file at the same `--at`, with `--side after` after the first (the "before" does not
change); put the pictures side by side for the person. The window does the same in its preview under the form.

### Profiles

- Run: `vs_cli.cmd run --operation profile_run --set profile=NAME --source ...`; `list profiles` names them.
- Save: `--set profile_name=NAME --set profile_preset=<preset id> --params values.json` where `values.json` is
  `{"profile_values": "{\"stock\": \"500T\"}", "profile_description": "..."}`, the cards of the encoder as `--set` or
  `--encoder`; it writes `config\profiles\NAME.json` (Latin letters, digits, `-`, `_`; a name taken needs `overwrite=true`).

### Install the engine

`describe` and `components` say what is missing. Ask `plan --operation install_vapoursynth` (and `install_vs_plugins`,
`install_ffmpeg`, `install_mlrt`) and tell the person the files and sizes before installing. Order: VapourSynth, plugins,
FFmpeg; MLRT only with an RTX card (`[PREFLIGHT] FAIL NVIDIA RTX` otherwise) - about 3.5 GB of downloads, trimmed to the
card; the first run of each model builds its TensorRT engine for 30-120 s. `remove_vapoursynth` moves the whole engine,
MLRT with it, to the Recycle Bin - ask first. Nothing is written outside the program folder. After the folder moves, the
next `vs_cli.cmd` or `system_core\doctor.py` repairs the launchers of the Pythons.

### Add or change a preset

1. The `.vpy` in `system_core\presets\<palette>\<id>.vpy`: it reads its fields from `os.environ["AUDION_VS_<FIELD>"]` with
   the manifest's defaults, loads the source by `al.load_source`, tags the output `_Range=al.source_range()` and goes
   through RGB with `range_s=al.range_name()`, adds grain by `al.add_grain` (a fixed seed), BM3D by `al.bm3d`, DFTTest by
   `al.dfttest`.
2. Its node in `config\tool_manifest.yaml` under its palette: `title`, `about`, `description` in both languages, `fields`
   with `label`/`label_ru`, `tooltip`/`tooltip_ru`; `accel: bm3d|mlrt` when PROCESSING moves something of it, `needs: mlrt`
   for vs-mlrt. The registry of the engine is read from the manifest.
3. Its place in `config\window_layout.yaml`: a mode in its section with `group` and `short`/`short_ru`.
4. `tests\` hold the manifest to the `.vpy` defaults and every operation to one place in the layout; then
   `vs_cli.cmd map --docs`, `Source\Tools\check_i18n.py` for a new text of the window, and `bench_presets`.

### Check the program

- The engine: `runtime\python.exe -m pytest -q -p no:cacheprovider tests` (about 20 s); every preset on a test clip:
  `vs_cli.cmd run --operation bench_presets --set frames=1` (the neural ones are passed over without MLRT);
  `system_core\doctor.py` - the whole stack; `install\verify_portable_env.cmd` - a release: the doctor, the console door,
  `Start.exe` and the window's own check.
- The window: `install\Build-App.cmd` runs the checks of the window, builds `App\` and lets the built window check itself;
  `pwsh -File Source\Tools\release-walk.ps1 -Stand <a folder that does not exist yet>` presses its buttons by UI
  Automation on a copy of the program, off the screen (an installed PowerShell 7); `Source\Tools\shots.ps1 -To <folder>
  -Only <preset ids>` pictures pages of a Debug build (`dotnet build -c Debug` in `Source\`). Never the real mouse.

### Build

- The window: `install\Build-App.cmd` after a change in `Source\`; then `Source\bin`, `Source\obj`, `Source\Ps\bin`,
  `Source\Ps\obj` go to the Recycle Bin.
- The Python of the project and the tools: `builder_main.cmd` (FZF): 01/02 Python, 03 FZF, 10 VapourSynth, 11 plugins,
  12/13 FFmpeg, 14 remove VapourSynth, 15/16 MLRT, 70 clean the install cache, 71 doctor.
- The version is `config\version.json` alone.
