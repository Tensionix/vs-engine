# Changes

[Русский](CHANGELOG_RU.md) · [About the program](README_EN.md)

## 3.1.0

- The question of the additional components at the start: the button **OPEN SETUP** closes it and opens the sheet SETUP
  at once. "Later" still lasts until the next start: while a component is missing, the question is asked again.

## 3.0.0

**One program.** Audion VS Engine and Audion VS Engine Lite are one program now. The neural presets are shown by the
machine: with an NVIDIA RTX card SERVICE offers Install MLRT; without a card and without MLRT they are not in the window.

**New**
- A window on Avalonia (`Start.exe`, `App\AudionVSEngine.exe`): palettes, presets in groups by the kind of processing,
  forms with sliders, the cards of the encoder, remembered paths with history and pins, a terminal with the progress of
  every frame, STOP.
- The preview: the middle frame of a video of the Source before and after the preset with the values of the form, counted
  by itself when the form is left alone; before, after or side by side; the videos of the Source in turn.
- The console command `vs_cli.cmd`: every operation, the outcome as JSON, exit codes, `--dry-run`, a stop file, `frame` —
  a frame before and after as PNG; `describe`, `list`, `map`, `components`, `plan`.
- Presets: IMAX 70mm, Anamorphic Scope, Polaroid; with MLRT — DPIR Denoise, Real-ESRGAN 2x, Soft HD Rebuild 2x. 28
  presets in all. RIFE Interpolation of the full edition 2.0.3 is out: on an RTX 5070 TensorRT (10.16, 11.1, TensorRT-RTX
  1.5) builds wrong frames between the frames; DirectML gives right ones only through ONNX Runtime, whose vs-mlrt plugin
  exists only for the old interface VapourSynth R80+ does not load; on the processor a new 4K frame takes 1.28 s — about
  half an hour for a minute of 24p doubled to 48p. In detail — [Decisions](DECISIONS_EN.md#no-frame-interpolation).
- The denoisers measure the noise of the source and grow with it (`noise=auto`); `noise=fixed` keeps the settings.
- A preset runs on a file or on a whole folder with its subfolders; the results keep its folders.
- SAVE A PROFILE on the page of a preset.
- SETUP in the header: the additional components - VapourSynth, its plugins, FFmpeg, MLRT with an RTX card - with
  their versions, INSTALL, UPDATE and INSTALL ALL; at every start the window offers to install the ones not yet here,
  or says where SETUP is.
- The installers say what they will download before they start; the engine can be removed to the Recycle Bin.

**Changed**
- FFmpeg by the NVIDIA driver: the newest stable Gyan build, 9.0.2 at least, without an NVIDIA card and from the LTS
  driver 610.88; a newer build that fails the NVENC test goes back to 9.0.2. Below 610.88 an older branch keeps NVENC
  working, and the installer, the plan of the download and the badge of FFmpeg say that not every operation is
  possible. The window compares FFmpeg with the newest release; SETUP updates it.
- The newest stable VapourSynth with plugins built for its interface; the set of plugins does not move the engine.
- BM3D on the video card through Vulkan, on a card of any maker; without one — on the processor. PROCESSING is
  Auto / CPU / GPU and stands only on the presets where it changes something.
- The result goes into `<Target>\<Palette>\<preset>_<encoder>\`, the name of the source kept.
- A result already there is passed over unless *Overwrite*; a result is written under a name of its own until it is whole.
- The output keeps the colour range of the source, through the filters and into the encoder.
- The grain has a fixed seed: the same file gives the same frames.
- The indexes of the sources are written into the program's folder, not beside the source.
- Inverse telecine refuses a source under 29 fps.
- Camera RAW in the Source - ProRes RAW, ARRIRAW, Sony RAW / X-OCN, RED R3D, Nikon N-RAW, Blackmagic RAW, Canon Cinema
  RAW - is said in one line with the program that opens it and its page, the engine does not read it: a Source of it
  alone is refused before the run, among other videos it fails by itself; the preview says the same.
- A value outside its range or not among its choices is refused with the reason.

**Fixed**
- ProRes into MXF stopped before its first frame when the source had AAC or 44.1 kHz sound: MXF gets PCM 24 bit at 48 kHz.
- The sources of a former FFmpeg build are removed when the new build's are in place.
- STOP no longer leaves a half-written file that a later run took for a finished one.
- The folders of the program are cleared through the Recycle Bin.
- Three built-in profiles named an encoder that did not exist; they use `h264_crf14`.
- Real-ESRGAN: the models General and General, denoise ran the anime model, as vs-mlrt has no general model of
  Real-ESRGAN; they are gone, Anime is the default, and a model vs-mlrt lacks is refused by name.

## 2.0.3

The last version of the two editions: the full one with the neural presets and Lite without them, a window in a web view,
22 presets in Lite.
