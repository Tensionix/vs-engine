# Audion VS Engine

<!-- audion:release -->
<p align="center">
  <a href="https://audion.dev/downloads/vs-engine"><img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0b6db8?style=flat-square&logo=windows&logoColor=white"></a>
  <a href="https://github.com/Tensionix/vs-engine/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/Tensionix/vs-engine?style=flat-square&label=release&color=e08a63"></a>
  <a href="https://github.com/Tensionix/vs-engine/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/Tensionix/vs-engine/total?style=flat-square&label=downloads&color=5fd08a"></a>
  <a href="https://github.com/Tensionix/vs-engine/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/Tensionix/vs-engine?style=flat-square&color=5fd08a&logo=apache&logoColor=white&cacheSeconds=3600"></a>
</p>

**Version 2.0.2** · 2026-09-04 · 7.8 MB

- [Direct download](https://dl.audion.dev/vs-engine/2.0.2/Audion_VS_Engine_v2.0.2.zip) — unmetered, no rate limits
- [Project page](https://audion.dev/downloads/vs-engine) — every version and how to install

<p align="center"><img src="docs/screenshot.png" alt="The program window" width="560"></p>

`SHA-256: 5cd9e89aef35167bfb204e8f4a014c3683f7eac4e84d85dc1191d363d27f6e47`

---

An **Audion** tool, published by [Tensionix](https://github.com/Tensionix).
<!-- /audion:release -->


[Русский](Docs/README_RU.md) · [User Guide](Docs/USER_GUIDE_EN.md)

**Contents**

- [Why It Exists](#why-it-exists)
- [Four Palettes](#four-palettes)
- [The Principle](#the-principle)
- [Editions](#editions)
- [Next](#next)
- [Technical Reference](#technical-reference)

Technical video preparation and stylisation on VapourSynth and FFmpeg.
Twenty-eight presets across four independent palettes.

## Why It Exists

VapourSynth does what no editing suite offers out of the box: restoring film
material, deinterlacing with a good algorithm, denoising that treats the shadows
separately, neural upscaling. But using it means writing a Python script,
remembering plugin names, and assembling a pipeline by hand for every clip.

This program turns that into a set of ready presets. The script stays under the
hood: the engine assembles a `vspipe | ffmpeg` chain and runs it.

## Four Palettes

They are independent: you can take the technical processing alone and never touch
the stylisation, or the reverse.

| palette | presets | what it does |
|---|---|---|
| **Precision** | 8 | denoising, including shadow-targeted, debanding, controlled return of fine grain. The technical layer **before** the colourist |
| **Film** | 7 | film emulations: 35 mm Kodak, 16 mm, Super 8, bleach bypass, IMAX 70 mm, a general cinematic look |
| **Retro** | 3 | analogue character: VHS and CRT, a 1990s camcorder, Polaroid |
| **Restoration** | 10 | what editing suites lack: deinterlacing, inverse telecine, motion-compensated denoising, derainbow and deblocking, dehazing, plus neural upscaling and frame doubling |

**Order matters.** The precision palette is the technical layer that comes
*before* colour grading: fixing noise after the colourist has lifted the shadows
is too late.

## The Principle

The engine is a Python orchestrator over `vspipe | ffmpeg`. It neither rewrites
VapourSynth nor hides it: the assembled command is visible, and you can take it
and run it by hand.

The launchers are ordinary batch files with a quick picker and a fallback menu, in
Russian and English versions.

## Editions

| edition | presets | difference |
|---|---|---|
| **full** | 28 | with the neural layer: upscaling, frame doubling, neural denoising |
| Lite | 22 | classic VapourSynth plugins, no neural stack |

Lite is lighter and needs no graphics card for the heavy operations.

## Next

* [User Guide](Docs/USER_GUIDE_EN.md) — installing the engine, first run, palettes,
  profiles, command line.

---

## Technical Reference

### Before the First Run

The VapourSynth engine and its plugins are installed separately — once. Until
that is done, the presets will not run.

### FFmpeg and the NVIDIA Driver

Every FFmpeg build is compiled against a particular version of the
hardware-encoding headers and demands its own minimum driver. The newest build on
an old driver does not accelerate anything — it breaks the hardware path. The
build is chosen to match the driver.

### Profiles

Saved combinations of presets and parameters — so the same chain need not be
assembled twice.

### CUDA

Needed only for the neural layer and only on NVIDIA cards. Setup is covered in
the user guide as a separate section.
