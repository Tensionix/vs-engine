# Audion VS Engine — Operations

**Contents**

- [Presets](#presets)
  - [PRECISION](#precision)
  - [FILM LOOKS](#film-looks)
  - [RETRO](#retro)
  - [RESTORATION](#restoration)
  - [PROFILES](#profiles)
- [Every preset and profile: processing, encoding, run](#every-preset-and-profile-processing-encoding-run)
- [SETUP: the additional components](#setup-the-additional-components)
- [SERVICE: checks](#service-checks)
- [Encoders](#encoders)

> Made from the data of the program by `vs_cli.cmd map --docs`: the manifest of the operations (`config\tool_manifest.yaml`) and the layout of the window (`config\window_layout.yaml`). It is not edited by hand: a text is changed there and the command is run again.

## Presets

### PRECISION

Denoise, deband, grain

#### Mild Denoise (`mild_denoise`)

*Any noise, any machine*. Spectral denoise with DFTTest on the CPU.

Call: `vs_cli.cmd run --operation mild_denoise`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `strength` Strength | choice | `medium` | `light` Light, `medium` Medium, `strong` Strong | DFTTest sigma: light 4, medium 8, strong 14. |
| `noise` Noise | choice | `auto` | `auto` Auto, `fixed` Fixed | Auto: the strength follows the noise measured in the source and never goes below the setting. Fixed: the setting as it is. |

#### Shadow Denoise SOTA (`shadow_denoise_sota`)

*BM3D in the shadows only*. BM3D on float, held to the shadows by a luma mask; micro-grain put back so the shadows are not plastic.

Call: `vs_cli.cmd run --operation shadow_denoise_sota`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `sigma` BM3D sigma | number | `2.5` | 1.0 … 4.0, step 0.1 | BM3D strength on the luma; the colour gets 0.6 of it. |
| `noise` Noise | choice | `auto` | `auto` Auto, `fixed` Fixed | Auto: the strength follows the noise measured in the source and never goes below the setting. Fixed: the setting as it is. |
| `grain_back` Grain back | number | `0.6` | 0.0 … 2.0, step 0.05 | Micro-grain put back over the cleaned shadows; 0 - none. |
| `shadow_threshold` Shadow threshold | number | `0.2` | 0.0 … 0.5, step 0.01 | The brightness (0..1) where the shadows end. |
| `transition` Mask transition | number | `0.1` | 0.01 … 0.4, step 0.01 | How wide the smooth passage below the threshold is: the shadows are cleaned fully this far under it, less and less up to it. |
| `preview_mask` Show mask | tick | `false` |  | The result is the shadow mask itself, not the picture: for setting the threshold. |

#### Chroma Cleanup (`chroma_cleanup`)

*Colour noise only*. DFTTest on the colour planes only: the colour noise goes, the luma is not touched.

Call: `vs_cli.cmd run --operation chroma_cleanup`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `strength` Strength | choice | `medium` | `light` Light, `medium` Medium, `strong` Strong | Sigma on the colour: light 6, medium 12, strong 20. |
| `noise` Noise | choice | `auto` | `auto` Auto, `fixed` Fixed | Auto: the strength follows the noise measured in the source and never goes below the setting. Fixed: the setting as it is. |

#### Deband Safe (`deband_safe`)

*Smooth gradients, no grain*. neo_f3kdb lightly: the steps of gradients go, no grain is added.

Call: `vs_cli.cmd run --operation deband_safe`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `range` Deband range | number | `12` | 8 … 32, step 1 | How far neo_f3kdb looks for the neighbours it smooths with; larger - stronger. |
| `y` Y threshold | number | `48` | 0 … 128, step 1 | neo_f3kdb threshold of the luma: how strong a step of brightness is still smoothed. |
| `cb` Cb threshold | number | `32` | 0 … 128, step 1 | neo_f3kdb threshold of the blue-difference colour plane. |
| `cr` Cr threshold | number | `32` | 0 … 128, step 1 | neo_f3kdb threshold of the red-difference colour plane. |

#### Deband Fine Grain (`deband_fine_grain`)

*Gradients and micro-texture*. neo_f3kdb, then AddGrain puts a fine texture back over the smoothed gradients.

Call: `vs_cli.cmd run --operation deband_fine_grain`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `range` Deband range | number | `14` | 8 … 32, step 1 | How far neo_f3kdb looks for the neighbours it smooths with; larger - stronger. |
| `y` Y threshold | number | `48` | 0 … 128, step 1 | neo_f3kdb threshold of the luma: how strong a step of brightness is still smoothed. |
| `cb` Cb threshold | number | `32` | 0 … 128, step 1 | neo_f3kdb threshold of the blue-difference colour plane. |
| `cr` Cr threshold | number | `32` | 0 … 128, step 1 | neo_f3kdb threshold of the red-difference colour plane. |
| `grain_var` Grain variance | number | `0.6` | 0.0 … 2.0, step 0.05 | AddGrain variance on the luma; the colour gets 0.27 of it. |

#### Filmic Rebuild (`filmic_rebuild`)

*Denoise, deband, grain*. BM3D, then neo_f3kdb, then grain laid by brightness: the digital noise and banding go, a controlled grain comes.

Call: `vs_cli.cmd run --operation filmic_rebuild`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `sigma` BM3D sigma | number | `2.0` | 1.0 … 3.5, step 0.1 | BM3D strength on the luma; the colour gets 0.6 of it. |
| `noise` Noise | choice | `auto` | `auto` Auto, `fixed` Fixed | Auto: the strength follows the noise measured in the source and never goes below the setting. Fixed: the setting as it is. |
| `deband_range` Deband range | number | `14` | 8 … 32, step 1 | How far neo_f3kdb looks for the neighbours it smooths with; larger - stronger. |
| `grain_shadow` Grain in shadows | number | `1.5` | 0.0 … 3.0, step 0.05 | Grain variance laid where the picture is darker than the shadow threshold. |
| `grain_mid` Grain in mid-tones | number | `0.9` | 0.0 … 3.0, step 0.05 | Grain variance laid between the two thresholds. |
| `grain_high` Grain in highlights | number | `0.4` | 0.0 … 3.0, step 0.05 | Grain variance laid where the picture is brighter than the highlight threshold. |
| `shadow_threshold` Shadow threshold | number | `0.3` | 0.0 … 0.5, step 0.01 | The brightness (0..1) where the shadows end. |
| `high_threshold` Highlight threshold | number | `0.65` | 0.5 … 1.0, step 0.01 | The brightness (0..1) where the highlights begin. |

#### Archive Clean (`archive_clean`)

*Neutral master, no grain*. DFTTest lightly and neo_f3kdb lightly, no grain: a neutral master for the archive.

Call: `vs_cli.cmd run --operation archive_clean`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `denoise` Denoise | choice | `light` | `light` Light, `medium` Medium, `strong` Strong | DFTTest sigma: light 4, medium 8, strong 14. |
| `noise` Noise | choice | `auto` | `auto` Auto, `fixed` Fixed | Auto: the strength follows the noise measured in the source and never goes below the setting. Fixed: the setting as it is. |
| `range` Deband range | number | `10` | 8 … 32, step 1 | How far neo_f3kdb looks for the neighbours it smooths with; larger - stronger. |

#### Pregrade Prep (`pregrade_prep`)

*Minimum touch before Resolve*. A very light DFTTest and nothing else: the material goes to grading almost as it was.

Call: `vs_cli.cmd run --operation pregrade_prep`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `strength` Strength | choice | `light` | `light` Light, `medium` Medium | DFTTest sigma: light 3, medium 6. |
| `noise` Noise | choice | `auto` | `auto` Auto, `fixed` Fixed | Auto: the strength follows the noise measured in the source and never goes below the setting. Fixed: the setting as it is. |

### FILM LOOKS

The looks of film stocks

#### Film 35mm (`film_35mm`)

*Kodak 35 mm, three stocks*. A Kodak 35 mm look with the stock to choose: 250D, 500T or 50D.

Call: `vs_cli.cmd run --operation film_35mm`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `stock` Stock | choice | `250D` | `250D` 250D, `500T` 500T, `50D` 50D | 250D - daylight, neutral; 500T - tungsten, cooler; 50D - the cleanest. |
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |

#### Film 16mm (`film_16mm`)

*Softer, grainier, lifted blacks*. A 16 mm feel: heavier softness, visible grain, lifted blacks.

Call: `vs_cli.cmd run --operation film_16mm`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |

#### Super 8 (`super8`)

*Heaviest grain, faded 70s*. Super 8: the heaviest grain, the softest optics, the faded contrast of the 70s.

Call: `vs_cli.cmd run --operation super8`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |

#### IMAX 70mm (`imax_70mm`)

*Large format, the finest grain*. A 65/70 mm IMAX feel: minimal grain, a gentle halation of the highlights, a weave of the gate up to 2 pixels.

Call: `vs_cli.cmd run --operation imax_70mm`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |
| `gate_weave` Gate weave | tick | `true` |  | Every frame moves by up to 2 pixels, as film does in the gate of a projector; off - the picture stands still. One file gives the same weave every time. |

#### Cinematic (`cinematic`)

*A subtle film look, safe*. A universal subtle film look for any material.

Call: `vs_cli.cmd run --operation cinematic`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |

#### Bleach Bypass (`bleach_bypass`)

*Hard contrast, little colour*. High contrast, desaturated, harsh - the look of a bleach bypass print.

Call: `vs_cli.cmd run --operation bleach_bypass`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |

#### Anamorphic Scope (`anamorphic_scope`)

*Blue streaks, teal shadows*. The cinemascope look: horizontal blue lens flares on the highlights alone and cool teal shadows.

Call: `vs_cli.cmd run --operation anamorphic_scope`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |
| `flare_len` Flare length | number | `96` | 32 … 256, step 1 | The length of a streak in pixels: longer - more dramatic. |
| `flare_thr` Flare threshold | number | `0.78` | 0.0 … 1.0, step 0.01 | From what brightness a highlight flares: lower - more of the picture flares. |
| `teal_shadow` Teal shadows | number | `0.35` | 0.0 … 1.0, step 0.05 | The strength of the cool teal tint in the shadows. |

### RETRO

VHS, CRT, camcorder

#### VHS CRT (`vhs_crt`)

*Tape, bleed, analog noise*. Composite video, VHS, a CRT: the colour bleeds, the picture is soft, analog noise.

Call: `vs_cli.cmd run --operation vhs_crt`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |

#### Camcorder 90s (`camcorder_90s`)

*A home camera of the 90s*. A consumer camcorder: softer than VHS, slightly overexposed, a mild colour bleed.

Call: `vs_cli.cmd run --operation camcorder_90s`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |

#### Polaroid (`polaroid`)

*An instant photo of the 70s and 80s*. A Polaroid SX-70 feel: a candy bloom of the highlights, warm cream midtones, darker corners.

Call: `vs_cli.cmd run --operation polaroid`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `intensity` Intensity | number | `1.0` | 0.0 … 2.0, step 0.05 | The strength of the whole look: 0 - off, 1 - as tuned, 2 - heavy. |
| `vignette` Vignette | number | `0.55` | 0.0 … 1.0, step 0.05 | How dark the corners go: 0 - no vignette, 1 - the corners go black. |

### RESTORATION

Deinterlace, telecine, artefacts

#### QTGMC Deinterlace (`qtgmc_deinterlace`)

*Interlaced video to progressive*. QTGMC (NNEDI3 and MVTools): the reference deinterlacer for interlaced sources.

Call: `vs_cli.cmd run --operation qtgmc_deinterlace`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `field_order` Field order | choice | `tff` | `tff` TFF, `bff` BFF | TFF - top field first (broadcast, HDV, DV NTSC); BFF - bottom field first (DV PAL). |
| `preset` QTGMC preset | choice | `Medium` | `Draft` Draft, `Ultra Fast` Ultra Fast, `Super Fast` Super Fast, `Very Fast` Very Fast, `Faster` Faster, `Fast` Fast, `Medium` Medium, `Slow` Slow, `Slower` Slower, `Very Slow` Very Slow, `Placebo` Placebo | Speed against quality: Draft is the fastest, Placebo the slowest. |
| `output_fps` Output frame rate | choice | `single` | `single` Single, `double` Double | Single - the frame rate of the source; double - twice as many frames, the smoothest motion. |

#### TIVTC IVTC (`tivtc_ivtc`)

*NTSC 29.97 back to 23.976*. TIVTC takes the 3:2 pulldown out of telecined NTSC: 29.97 fps back to 23.976 fps progressive.

Call: `vs_cli.cmd run --operation tivtc_ivtc`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `pp` TFM post-processing | number | `6` | 0 … 7, step 1 | 0 - off ... 7 - deinterlace whatever does not match. |
| `cycle` Cycle | number | `5` | 2 … 25, step 1 | The TDecimate cycle in frames; 5 for a standard NTSC telecine. |
| `rdrop` Drop per cycle | number | `1` | 1 … 5, step 1 | Frames dropped from each cycle; 1 of 5 for NTSC. |

#### MVTools MCDegrain (`mvtools_mcdegrain`)

*Noise by motion, detail kept*. Temporal denoise along the motion (MVTools and MDegrain): the noise goes, the detail stays sharp.

Call: `vs_cli.cmd run --operation mvtools_mcdegrain`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `radius` Radius | number | `2` | 1 … 3, step 1 | How many frames before and after are taken. |
| `thsad` THSAD | number | `200` | 100 … 400, step 1 | The threshold of a block's difference; higher - more averaging. |
| `noise` Noise | choice | `auto` | `auto` Auto, `fixed` Fixed | Auto: the strength follows the noise measured in the source and never goes below the setting. Fixed: the setting as it is. |
| `blksize` Block size | choice | `16` | `8` 8, `16` 16 | The block of the motion search: 16 for SD and HD, 8 for fine detail and 4K. |

#### DPIR Denoise (`dpir_denoise`)

*A neural denoise of heavy noise*. DPIR on vs-mlrt: heavy noise and high ISO go, the texture stays - where BM3D smears the picture.

Call: `vs_cli.cmd run --operation dpir_denoise`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `strength` Strength | number | `10.0` | 1.0 … 50.0, step 0.5 | The level of noise the network expects: 10 - medium, 15 - heavy, 25 - very heavy. |
| `model` Model | choice | `drunet_color` | `drunet_color` Colour, `drunet_gray` Grey, `drunet_deblocking_color` Blocks, colour, `drunet_deblocking_gray` Blocks, grey | Colour - colour video; Blocks - the blocks of JPEG and MPEG as well; Grey - the brightness alone, the colour kept as it is. |
| `tile` Tile | number | `384` | 256 … 512, step 16 | The piece of the frame the network takes at a time, in pixels: smaller - less video memory, slower. |

#### Deblock H.264 Artefacts (`deblock_h264_artefacts`)

*Over-compressed H.264 and MPEG*. Deblock_QED of havsfunc, aware of edges: for over-compressed H.264 and MPEG - web rips, messenger re-encodes, weak broadcast.

Call: `vs_cli.cmd run --operation deblock_h264_artefacts`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `quant1` Quant 1 | number | `24` | 16 … 32, step 1 | The strength on the edges of the blocks; higher - stronger. |
| `quant2` Quant 2 | number | `26` | 16 … 32, step 1 | The strength inside the blocks. |
| `aoffset` Alpha offset | number | `1` | 0 … 2, step 1 | How sensitive the filter is to edges. |
| `boffset` Beta offset | number | `1` | 0 … 2, step 1 | How sensitive the filter is inside the blocks. |

#### Derainbow Decross (`derainbow_decross`)

*Composite rainbow and dot crawl*. Smoothing of the colour along the motion (MVTools): the rainbow, dot crawl and cross colour of NTSC composite go, the luma is not softened.

Call: `vs_cli.cmd run --operation derainbow_decross`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `strength` Strength | number | `0.6` | 0.0 … 1.0, step 0.05 | How strongly the colour is smoothed; 0 - as it was, 1 - fully. |
| `blksize` Block size | choice | `16` | `8` 8, `16` 16 | The block of the motion search: 16 for SD and HD, 8 for fine detail and 4K. |

#### Dehaze Local Contrast (`dehaze_local_contrast`)

*Clarity, no colour shift*. Local contrast, clarity and haze removal on the luma only: no colour shift, no halos.

Call: `vs_cli.cmd run --operation dehaze_local_contrast`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `strength` Strength | number | `1.0` | 0.0 … 2.0, step 0.05 | How much local contrast is added back; 0 - the picture as it was. |
| `radius` Radius | number | `8` | 1 … 16, step 1 | The size of the blur in pixels: larger - haze, smaller - clarity. |

#### NNEDI3 Upscale 2X (`nnedi3_upscale_2x`)

*Twice the size, no ML*. NNEDI3 enlarges the picture twice, the same every run, without a neural network.

Call: `vs_cli.cmd run --operation nnedi3_upscale_2x`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `quality` Quality | choice | `balanced` | `fast` Fast, `balanced` Balanced, `best` Best | Fast - a lighter NNEDI3; balanced - as tuned; best - slower, cleaner edges. |
| `chroma` Colour upscale | choice | `spline36` | `spline36` Spline36, `nnedi3` NNEDI3 | Spline36 is the safer one; NNEDI3 is sharper and slower. |

#### Real-ESRGAN 2x (`vsmlrt_realesrgan_2x`)

*A neural upscale, twice the size*. Real-ESRGAN on vs-mlrt: drawn animation twice the size, its lines clean and sharp; TensorRT on NVIDIA.

Call: `vs_cli.cmd run --operation vsmlrt_realesrgan_2x`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `model` Model | choice | `animevideov3` | `animevideov3` Anime, `animejanaiV2-L1` AnimeJaNai 1, `animejanaiV2-L2` AnimeJaNai 2, `animejanaiV2-L3` AnimeJaNai 3 | Real-ESRGAN in vs-mlrt has models for drawn animation alone: Anime is the lightest, AnimeJaNai 1-3 go from lighter to stronger. Live action they can over-sharpen. |
| `tile` Tile | number | `384` | 256 … 768, step 16 | The piece of the frame the network takes at a time, in pixels: smaller - less video memory, slower. |
| `tile_pad` Tile overlap | number | `16` | 4 … 64, step 1 | How far the pieces overlap, in pixels, so that their seams do not show. |

#### Soft HD Rebuild 2x (`soft_hd_rebuild_2x`)

*Soft HD rebuilt at twice the size*. A spectral cleanup, then Real-ESRGAN: soft and undersampled HD rebuilt at twice the size without its noise blown up.

Call: `vs_cli.cmd run --operation soft_hd_rebuild_2x`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `rebuild` Rebuild | choice | `balanced` | `conservative` Careful, `balanced` Balanced, `aggressive` Strong | How much detail comes back: Careful - no halos, Strong - for very soft sources. |
| `cleanup` Cleanup | choice | `medium` | `light` Light, `medium` Medium, `strong` Strong | The cleanup before the network, so that it does not enlarge the noise and the blocks. |
| `model` Model | choice | `animevideov3` | `animevideov3` Anime, `animejanaiV2-L1` AnimeJaNai 1, `animejanaiV2-L2` AnimeJaNai 2, `animejanaiV2-L3` AnimeJaNai 3 | Real-ESRGAN in vs-mlrt has models for drawn animation alone: Anime is the lightest, AnimeJaNai 1-3 go from lighter to stronger. Live action they can over-sharpen. |
| `tile` Tile | number | `384` | 256 … 768, step 16 | The piece of the frame the network takes at a time, in pixels: smaller - less video memory, slower. |
| `tile_pad` Tile overlap | number | `16` | 4 … 64, step 1 | How far the pieces overlap, in pixels, so that their seams do not show. |

### PROFILES

Saved presets on a file or a folder

#### Run a profile (`profile_run`)

*A saved preset with its settings*. A profile - a preset with its settings and its encoder, saved under a name - run on a file or on a whole folder.

Call: `vs_cli.cmd run --operation profile_run`

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `profile` Profile | choice | `` | from `profile_options` | The profiles of config\profiles. Choosing one sets its encoder on the cards. |

## Every preset and profile: processing, encoding, run

These fields stand on every page: the processing and the cards of the encoder are one for the whole window, set on one page they are set on all.

| Field | Kind | Default | Choices | What it is |
|---|---|---|---|---|
| `vs_accel` Processing | choice | `auto` | `auto` Auto, `cpu` CPU, `gpu` GPU | Where BM3D runs. Auto: on the video card when VapourSynth sees a working Vulkan device, else on the CPU. The other filters always run on the CPU. |
| `encode_family` Codec | choice | `x264` | `x264` x.264, `x265` x.265, `prores` ProRes, `dnxhr` DNxHR | What the result is written with. |
| `encode_backend` Encoder | choice | `cpu` | `cpu` CPU, `nvenc` NVIDIA, `qsv` QuickSync, `amf` AMF | The CPU or the hardware encoder of the video card. A hardware one this machine has not passed (SERVICE - Hardware capabilities) is off. (shown when encode_family is one of x264, x265) |
| `encode_quality` Quality | choice | `14` | `14` 14, `17` 17, `21` 21 | 14 - near lossless, for the archive; 17 - almost invisible losses; 21 - web, proxy, preview. (shown when encode_family is one of x264, x265) |
| `encode_container` Container | choice | `mp4` | `mp4` MP4, `mkv` MKV | The file x.264 and x.265 are written into. (shown when encode_family is one of x264, x265) |
| `prores_profile` ProRes profile | choice | `lt` | `lt` LT, `422` 422, `hq` HQ | LT is enough for grading; HQ for keying and repeated passes. (shown when encode_family is prores) |
| `prores_wrapper` Wrapper | choice | `mov` | `mov` MOV, `mxf` MXF | MOV for Resolve and Final Cut; MXF for Premiere and Avid. (shown when encode_family is prores) |
| `dnxhr_profile` DNxHR profile | choice | `hq` | `hq` HQ, `hqx` HQX, `lb` LB, `sq` SQ | LB - low bandwidth, SQ - standard, HQ - high quality, HQX - 10 bit. (shown when encode_family is dnxhr) |
| `overwrite` Overwrite | tick | `false` |  | Make the result again where it is already there. Off: a file that is already done is passed over. |

**Where the result goes.** `<Target>\<Palette>\<preset>_<encoder>\<the folders of the Source>\<name>.<ext>`; a profile - `<Target>\Profiles\<profile>_<encoder>\...`. The name of the source is kept. A result that is there is passed over unless *Overwrite*.

## SETUP: the additional components

| Operation | What it is | Call |
|---|---|---|
| Install VapourSynth | The newest stable portable VapourSynth into system_core\vapoursynth (step 10 of the builder). | `vs_cli.cmd run --operation install_vapoursynth` |
| Install the plugins | The plugins of install\vs_plugins.json into VapourSynth (step 11 of the builder); the core is not moved. | `vs_cli.cmd run --operation install_vs_plugins` |
| Install FFmpeg | FFmpeg of Gyan into Tools\ffmpeg by the NVIDIA driver: the newest stable, 9.0.2 at least, without an NVIDIA card and from the LTS driver 610.88; below it 8.0.1 (570-610.87) or 7.1 so that NVENC works, and not every operation is possible (step 13 of the builder). | `vs_cli.cmd run --operation install_ffmpeg` |
| Install MLRT | vs-mlrt - TensorRT, ONNX Runtime and the models - into VapourSynth, trimmed to this video card: the neural presets DPIR, Real-ESRGAN and Soft HD Rebuild. Offered at the first start and in SETUP when an NVIDIA RTX card is found; the builder does not install it. | `vs_cli.cmd run --operation install_mlrt` |
| Remove VapourSynth | The folder of the engine, system_core\vapoursynth, with its plugins and MLRT, goes to the Recycle Bin (step 14 of the builder). | `vs_cli.cmd run --operation remove_vapoursynth` |

## SERVICE: checks

| Operation | What it is | Call |
|---|---|---|
| Doctor | Checks the whole engine: the two Pythons, VapourSynth, every plugin, FFmpeg, BM3D on the video card. | `vs_cli.cmd run --operation doctor` |
| File list | The videos of the Source the next run takes, with their folders. | `vs_cli.cmd run --operation source_list` |
| Hardware capabilities | Short FFmpeg encodes with NVENC, QuickSync and AMF: which hardware encoders work on this machine. | `vs_cli.cmd run --operation hardware_capabilities` |
| Check every preset | Every preset on a test clip, a frame each: what runs on this machine and how fast. | `vs_cli.cmd run --operation bench_presets` |
| BM3D: video card or CPU | BM3D through Vulkan (bm3dvk) against BM3D on the CPU (bm3d) on the first video of the Source: frames a second of each. | `vs_cli.cmd run --operation bench_gpu` |
| Source info | What ffprobe knows of every video of the Source: size, frame rate, length, codec, range, colour. | `vs_cli.cmd run --operation probe_source` |
| Save a profile | The settings of a preset and the encoder of the cards saved as a profile in config\profiles. | `vs_cli.cmd run --operation profile_save` |

## Encoders

| Encoder | Cards |
|---|---|
| `dnxhr_hq` | `encode_family=dnxhr`, `dnxhr_profile=hq` |
| `dnxhr_hqx` | `encode_family=dnxhr`, `dnxhr_profile=hqx` |
| `dnxhr_lb` | `encode_family=dnxhr`, `dnxhr_profile=lb` |
| `dnxhr_sq` | `encode_family=dnxhr`, `dnxhr_profile=sq` |
| `h264_amf_q14` | `encode_family=x264`, `encode_backend=amf`, `encode_quality=14`, `encode_container=mp4` |
| `h264_amf_q17` | `encode_family=x264`, `encode_backend=amf`, `encode_quality=17`, `encode_container=mp4` |
| `h264_amf_q21` | `encode_family=x264`, `encode_backend=amf`, `encode_quality=21`, `encode_container=mp4` |
| `h264_crf14` | `encode_family=x264`, `encode_backend=cpu`, `encode_quality=14`, `encode_container=mp4` |
| `h264_crf17` | `encode_family=x264`, `encode_backend=cpu`, `encode_quality=17`, `encode_container=mp4` |
| `h264_crf21` | `encode_family=x264`, `encode_backend=cpu`, `encode_quality=21`, `encode_container=mp4` |
| `h264_nvenc_q14` | `encode_family=x264`, `encode_backend=nvenc`, `encode_quality=14`, `encode_container=mp4` |
| `h264_nvenc_q17` | `encode_family=x264`, `encode_backend=nvenc`, `encode_quality=17`, `encode_container=mp4` |
| `h264_nvenc_q21` | `encode_family=x264`, `encode_backend=nvenc`, `encode_quality=21`, `encode_container=mp4` |
| `h264_qsv_q14` | `encode_family=x264`, `encode_backend=qsv`, `encode_quality=14`, `encode_container=mp4` |
| `h264_qsv_q17` | `encode_family=x264`, `encode_backend=qsv`, `encode_quality=17`, `encode_container=mp4` |
| `h264_qsv_q21` | `encode_family=x264`, `encode_backend=qsv`, `encode_quality=21`, `encode_container=mp4` |
| `h265_amf_q14` | `encode_family=x265`, `encode_backend=amf`, `encode_quality=14`, `encode_container=mp4` |
| `h265_amf_q17` | `encode_family=x265`, `encode_backend=amf`, `encode_quality=17`, `encode_container=mp4` |
| `h265_amf_q21` | `encode_family=x265`, `encode_backend=amf`, `encode_quality=21`, `encode_container=mp4` |
| `h265_crf14` | `encode_family=x265`, `encode_backend=cpu`, `encode_quality=14`, `encode_container=mp4` |
| `h265_crf17` | `encode_family=x265`, `encode_backend=cpu`, `encode_quality=17`, `encode_container=mp4` |
| `h265_crf21` | `encode_family=x265`, `encode_backend=cpu`, `encode_quality=21`, `encode_container=mp4` |
| `h265_nvenc_q14` | `encode_family=x265`, `encode_backend=nvenc`, `encode_quality=14`, `encode_container=mp4` |
| `h265_nvenc_q17` | `encode_family=x265`, `encode_backend=nvenc`, `encode_quality=17`, `encode_container=mp4` |
| `h265_nvenc_q21` | `encode_family=x265`, `encode_backend=nvenc`, `encode_quality=21`, `encode_container=mp4` |
| `h265_qsv_q14` | `encode_family=x265`, `encode_backend=qsv`, `encode_quality=14`, `encode_container=mp4` |
| `h265_qsv_q17` | `encode_family=x265`, `encode_backend=qsv`, `encode_quality=17`, `encode_container=mp4` |
| `h265_qsv_q21` | `encode_family=x265`, `encode_backend=qsv`, `encode_quality=21`, `encode_container=mp4` |
| `prores_422` | `encode_family=prores`, `prores_profile=422`, `prores_wrapper=mov` |
| `prores_422_mxf` | `encode_family=prores`, `prores_profile=422`, `prores_wrapper=mxf` |
| `prores_422hq` | `encode_family=prores`, `prores_profile=hq`, `prores_wrapper=mov` |
| `prores_422hq_mxf` | `encode_family=prores`, `prores_profile=hq`, `prores_wrapper=mxf` |
| `prores_lt` | `encode_family=prores`, `prores_profile=lt`, `prores_wrapper=mov` |
| `prores_lt_mxf` | `encode_family=prores`, `prores_profile=lt`, `prores_wrapper=mxf` |
