# a6600 (ILCE-6600) firmware 1.10 — open-gate / 3:2 video feasibility

Static analysis of the decrypted/extracted firmware. No hardware touched.

> Paths below use the layout produced by `scripts/extract_a6600.py <updater.exe> out`:
> `out/rootfs/` is the root filesystem (nflasha7), `out/usr/` is the `/usr`
> partition (nflasha15) and `out/system/` holds `av-cam.bin`, `vmlinux.bin` and
> the other camera images (nflasha3 FAT). Helpers are in `research/scripts/`,
> data outputs in `research/data/`.
Firmware version string: `38114_02.2020071501` (`out/rootfs/version.txt`).

All offsets are **file offsets** into the named file, not virtual addresses.

---

## 1. Component inventory

| Path | Size | Role (evidence) |
|---|---|---|
| `out/system/av-cam.bin` | 16,825,940 | Main camera/AV control firmware: imager driver (`IMX284`), ADF/AVIO pipeline, `LiroSeq` parameter checks, `[CODEC V]` open/start params, AVC/HEVC/AVCHD/JPEG control, `CapIdTblMgr`. Raw ARM image (header `0a 00 00 ea 4f 52 49 4c` = `b` + `"ORIL"`). |
| `out/usr/bin/orb-server` | 5,976,888 | ARM ELF, network/remote-control server. Only XAVC/AVCHD name strings, no geometry. |
| `out/usr/lib/libObj.so` | 20,889,004 | UI object layer. Holds `VALUEID_MOVIE_ASP_*`, `V_PICT_SIZE_*`, `PARAMID_MOVIE_*`, `PARAMID_CAP_INFO_*`, `ModelIdTable`. |
| `out/usr/lib/libmpr.so` | 12,741,872 | MPR media layer: `PICT_SIZE_*`, `MOVIE_FORMAT_TYPE_*`, `XavcMRecFltMgr`, `AviMMgr`, `VPictSize`, pixel-aspect/AVCHD metadata. |
| `out/usr/lib/libmprctrl.so` | — | Image-size tables grouped by aspect (see §2). |
| `out/usr/lib/viewUnified2.so` | 11,553,828 | Generic resolution table (same shape as libmprctrl). |
| `out/usr/lib/libInfraMediaCommon.so` | — | Contains one 1920x1280 u32 pair (generic media table). |
| `out/usr/lib/libSysDef.so` | 1,516,736 | `DefInh`/`DefRsrc`/`MwfTbl` tables (`CATEID_APP_MODELS`), no dimensions. |
| `out/usr/codec/vcd_firmware.bin` | 5,445,340 | Video codec DSP firmware (C++ style asserts only). |
| `out/usr/codec/bnl_firmware.bin`, `bnl_ipl.bin`, `bni_*` | 1.4 MB / … | “Beaune” codec DSP boot/firmware (`codec_drv.ko` loads them from `/usr/beaune/`). |
| `out/usr/sabin/sa_avce_*_zma.bin` | 227–231 KB | AVC **encoder** DSP tasks (quality / performance / performance+). |
| `out/usr/sabin/sa_avcd_*_zma.bin` | 68–87 KB | AVC **decoder** DSP tasks. |
| `out/usr/sabin/dcv_psf_table_movie*.bin` | 10–18 KB | **Not** geometry: PSF (point-spread / shading) correction tables. Headers say `IMX210` (`movie`, `movie_4k`) and `IMX094` (`movie_bayer`) — legacy shared files, not the a6600 sensor. |
| `out/usr/kmod/codec_drv.ko` | 18,372 | PCIe “Beaune” codec driver (`pci:v0000104Dd00009093`), no dimension constants. |
| `out/system/bonobo.bin` | 172,144 | ISP (“Bonobo”) firmware, no human-readable geometry. |
| `out/usr/scenario/CAMERA_SCN_MOVIE_REC_START.so` | 7,048 | Scenario glue, no sizes. |
| `out/a6600_updater.img` | 143,360 | Updater only: `bksb.elf`, `chkfirm.sh`, `pformat.elf`, `libupdaterbody.so`, … — **no** movie/encoder module (full string list in `research/data/updater_strings.txt`, 1694 lines). |

---

## 2. Dimension-table hits

### 2.1 `av-cam.bin` 0x834B14 — image-size table (7 entries × 24 bytes, repeated 3×)

Hexdump (`research/data/hex_avcam_834b10.txt`):

```
00834b10: 0100 0000 8002 0000 e001 0000 8002 0000   <- 0x1, 640, 480, 640
00834b20: e001 0000 0000 0000 2e0b 2400 8007 0000   <- 480, 0, 2362158, 1920
00834b30: 3804 0000 8007 0000 3804 0000 0000 0000   <- 1080, 1920, 1080, 0
00834b40: 3f0b 0500 a005 0000 3804 0000 c005 0000   <- 330559, 1440, 1080, 1472
```

Record = `{u32 w, u32 h, u32 stride_w, u32 stride_h, u32 flag, u32 value}`.

| offset | w×h | stride | flag | aspect |
|---|---|---|---|---|
| 0x834B14 | 640×480 | 640×480 | 0 | 4:3 |
| 0x834B2C | 1920×1080 | 1920×1080 | 0 | 16:9 |
| 0x834B44 | 1440×1080 | 1472×1080 | 0 | 4:3 (width crop) |
| 0x834B5C | **1620×1080** | 1664×1080 | 0 | **3:2 (width crop)** |
| 0x834B74 | 3840×2160 | 3840×2160 | 1 | 16:9 |
| 0x834B8C | 2880×2160 | 2880×2160 | 1 | 4:3 (width crop) |
| 0x834BA4 | **3240×2160** | 3264×2160 | 1 | **3:2 (width crop)** |

Identical copy at 0x834BBC and 0x834C64 (three copies = three size/quality classes).

Interpretation (proven): every 3:2 and 4:3 entry **keeps the same height as the 16:9 entry** (1080 or 2160) and is *narrower*. These are cropped stills taken out of a 16:9 video frame (Sony “Dual Rec” JPEG stills; `av-cam.bin` contains `FW: DualRecJpegTarget`, `CaptureUtilityJpegSize.cpp`, `FW: [%s] Invalid record size(...) cap mode / aspect / size type`). They are **not** taller-than-16:9 video frames.

### 2.2 `libmprctrl.so` 0x26924–0x26B4C — image size table grouped by aspect

Record = `{u32 w, u32 h, u32 aspect}`; aspect `2` = 16:9, `1` = 3:2, `0` = 4:3.

| offset | record | aspect list |
|---|---|---|
| 0x26924 | 6000×3376, 2 | 16:9 |
| 0x2695C | 1616×1080, 1 | 3:2 |
| 0x26968 | 1632×1088, 1 | 3:2 |
| **0x26974** | **1920×1280, 1** | **3:2 (still size)** |
| 0x26980 | 2048×1360, 1 | 3:2 |
| 0x26AC4 | 4240×2832, 1 | 3:2 |
| 0x26B30 | 6000×4000, 1 | 3:2 |
| **0x26C20** | **1920×1440, 0** | **4:3 (still size)** |
| 0x26B54… | 160×120, 640×480, 1080×810 … | 4:3 |

`1920x1280` and `1920x1440` exist here **only as generic still-image sizes**, next to sizes of other models (4240×2832 is the a7S-class L size; 2768×1848/1920×1280 are its M/S sizes). `viewUnified2.so` 0x813E9C–0x813F08 has the same flat table (`1920×1280`, `1920×1440` adjacent to `1440×1080`, `1600×1200`, `1632×1224`, …). `share/app/image_EVF.uxc` and `image_cmn_169.uxc` contain the same values as GUI/resource canvases.

### 2.3 `av-cam.bin` 0x9050E5 — video-format name table (enum debug names)

```
1280X720_24P / 1280X720_60_50P / 1920X1080_60_50I / 1920X1080_24P /
1920X1080_60_50P / …_PURE / 640X480_60_50P / 3840X2160_24P / 3840X2160_30_25P /
3840X2160_60_50P / 1280X720_120_100P / 800X480_240_200P / 1920X1080_120_100P /
1920X1080_240_200P / 1280X720_240_200P / 2048X1080_* / 4096X2160_* /
640X360_* / 480X270_* / 1440X1080_59_94I_50I / 1440X1080_23_98P / 1440X1080_29_97P_25P
```

Widths present: **480, 640, 800, 1280, 1440, 1920, 2048, 3840, 4096**. No 1620/2880/3240 and no height other than 270/360/480/720/1080/2160.

`4096X2160`/`2048X1080` prove this binary is shared with cinema-line models; presence of a name does **not** mean the a6600 exposes it.

### 2.4 UI movie-format placeholders — `libObj.so`

`<1280>28M 120p`, `<1280>50M 120p`, `<1920>50M 24p`, `<1920>50M 30p`,
`<1920>50M 60p`, `<3840>60M 24p`, `<3840>60M 30p` (also present in `a6600_fdat.bin`).
Only widths 1280/1920/3840 are offered by the UI.

---

## 3. Existing video modes found (static evidence)

Container/format enum (`libmpr.so` 0xB56980): `MOVIE_FORMAT_TYPE_AVCHD`, `M2PS`, `MP4_AVC_VGA`, `MP4_AVC_720`, `MP4_AVC_1080`, `DVAVI`, `XAVC`, `XAVC_HEVC`.

| Family | Frame | Aspect | Evidence |
|---|---|---|---|
| XAVC S 4K | 3840×2160 | 16:9 | `3840X2160_24P/30_25P/60_50P` (0x9051C3) |
| XAVC S HD | 1920×1080 | 16:9 | `1920X1080_24P/60_50P/120_100P/240_200P` |
| XAVC S HD | 1280×720 | 16:9 | `1280X720_*` |
| AVCHD | 1920×1080 | 16:9 | `1920X1080_60_50I` + `MOVIE_FORMAT_TYPE_AVCHD` |
| AVCHD | 1440×1080 (anamorphic) | 4:3 storage | `1440X1080_59_94I_50I` |
| Proxy / S&Q | 640×360, 480×270, 800×480 | 16:9 | `XAVC_PROXY_AVC/HEVC`, `800X480_240_200P` |
| (shared/cinema only) | 4096×2160, 2048×1080 | 17:9 / 2:1 | 0x90524E–0x9052D1 |

**Every real movie frame is 16:9.** The only non-16:9 “movie aspect” identifiers are legacy/AVCHD metadata, not frames:

* `VALUEID_MOVIE_ASP_16_9` (libObj 0x1096B82), `VALUEID_MOVIE_ASP_4_3` (0x1096B99), `VALUEID_MOVIE_ASP_15_9` (0x109EB5B) — **no `3_2` value exists**.
* `libmpr.so` 0xB2E2CF: `Normal( 4:3 )`, `Wide( 16:9 )`, `HFR( 15:9 )`; 0x965A6F: `pixelAspectRatio = [16:9] / [15:9] / [4:3]`; 0x9CAD89: `.16:9 .17:9 .15:9`. These are AVCHD/MPEG pixel-aspect and flag codes.

### The movie size model (why a taller frame has no representation)

`av-cam.bin` LiroSeq parameter checks use **enumerated geometry**, not free width/height:

```
FW: LiroSeq ParamCheckErr@%s[mov_aspect_req]   cur:%d req:%d
FW: LiroSeq ParamCheckErr@%s[movrec_mode_req]  cur:%d req:%d
FW: LiroSeq ParamCheckErr@%s[mov_size_req]     cur:%d req:%d
FW: LiroSeq ParamCheckErr@%s[mov_sizeh_req]    cur:%d req:%d
FW: LiroSeq ParamCheckErr@%s[e_set_img_frame_size] cur:%d req:%d
```

and the MPR enum is a **height class**:

```
libmpr.so   0xB56732: PICT_SIZE_VGA / PICT_SIZE_720 / PICT_SIZE_1080 / PICT_SIZE_2160 / PICT_SIZE_UNKNOWN
libObj.so   0x1021276 / 0x1030608 / 0x10332D5: V_PICT_SIZE_720 / VGA / WVGA / 1080 / 2160
```

So the pipeline picks `(pict_size_class, movie_aspect, rec_mode, frame_rate)` and derives pixel dimensions.
Height is quantised to **720 / 1080 / 2160**; width varies with the aspect enum. A 1280- or 1440-line frame has no enum value and no aspect value (3:2 absent), so the record-size validator
(`av-cam.bin` 0x9694E2: `FW: [%s] Invalid record size(%u, %u). Check image size backup value. cap mode: %u, aspect: %u, size type: %u`)
has nothing to match it against.

---

## 4. Encoder limits

* The codec interface is **fully parametric**; every open is logged with explicit geometry (`av-cam.bin` 0x90A370–0x90A84E):
  `picture_width`, `picture_height`, `canvas_size_x/y`, `valid_offset_x/y`, `valid_size_x/y`, `target_offset_x/y`, `target_size_x/y`, `input_image_chroma`, `es_buff_size`.
* No hard-coded width/height cap, macroblock limit, `MaxFS`, `level_idc` table or “size too large” check exists in `av-cam.bin`, `vcd_firmware.bin`, `codec_drv.ko`, `sa_avce_*` (searched strings and constant tables).
* Implied capability ceiling: **≥3840×2160** (the a6600 records 4K), and the shared build also carries `4096X2160` and `2048X1080` stream types. `PICT_SIZE_2160` is the largest size class.
* 1920×1280 = 120×80 macroblocks, 2,457,600 luma samples: within H.264 level 5.x and within a 4K-capable encoder. There is **no static evidence that the encoder itself would reject 1920×1280**. The obstacle is the mode/geometry model above, plus canvas/valid/target validation in the pipeline:
  `FW: %s: V DestSize Check Err: canvas[%d] valid[%d] offset[%d]` (0x969390) and `H DestSize Check Err` (0x969352).

---

## 5. Sensor readout modes

* Sensor identified as **IMX284** by RTTI in `av-cam.bin`: `N6Camera6Imager6IMX28419C_ImagerCtrl_IMX284E` (0x95338B), `N6Camera6Imager21ImagerDrvParam_IMX284E` (0x9533B8), `SB_Async/SB_ZpdFittingTbl_IMX284_DMHH.cpp` (0x9D4422). 6000×4000 is the a6600 still frame.
* The only rectangle blocks found (e.g. 0x857AD0 region: 6048×4108 active, 6024×4024 effective, 6000×4000 output, then 1376×1196 / 1736×1250 / 872×625) behave like lens shading / distortion-correction grids, not a readable mode table — 1376×1196, 1736×1250 and 872×625 are not plausible video readout modes and appear next to 6000×4000 without drive-mode/fps fields.
* **No 3:2 binning mode table** (e.g. 4240×2832, 2120×1416, 3000×2000, 6000×4000 at video rates) was found anywhere. 4240×2832 occurs only in still-size tables (`libmprctrl.so` 0x26AC4, `viewUnified2.so`).
* `dcv_psf_table_movie*.bin` are 144-entry × 74-byte signed correction tables (header `IMX210`/`IMX094`), **not** sensor modes.
* `sa_smod.bin` / `ssboot*.bin` / `bonobo.bin` contain no readable mode table.

Limitation: the imager mode table is not stored as plain dimensions in the accessible artifacts; the sensor driver’s `ModeRsvParam` table is compiled/encoded. Absence of a 3:2 readout mode is therefore **strong but not absolute**.

---

## 6. Gating / model checks

* `av-cam.bin` is a **shared multi-model binary** (contains DCI 4K 4096×2160 and 2048×1080 that the a6600 does not ship with). Feature availability is not decided by these strings.
* Gating is data-driven at runtime:
  * `FW: CapIdTblMgr) CheckCapIDAvailability ...` (0x9DFFxx region) — capability-ID table manager.
  * `PARAMID_CAP_INFO_STILL_ASPECT`, `PARAMID_CAP_INFO_STILL_SIZE`, `PARAMID_CAP_INFO_CAP_MODE` in `libObj.so`.
  * `ModelIdTable` / `ModelIdSoTable` in `libObj.so`; `CATEID_APP_MODELS` in `libSysDef.so`.
  * `ModelCautionConfig.so` is a 6.7 KB stub (`getCautionTable`, `getModeTable`, …) with no model data; `CautionConfig.so` (12 MB) is the shared caution-message table, not a feature matrix.
* No product-name string (`ILCE-6600`, model number, `CX883xx`) is present in the camera binaries; model identity comes from the backup/NAND config partitions, which are encrypted/compressed (`0110_backup/SYSASTRA-DSLR/CS/*.bin`, `0700_part_image/dev/nflasha5` = `WBI1` blob).
* Consequence: the a6600’s exact **enabled** mode list cannot be read from strings. It must be inferred from the enum/table structure + known product behaviour.

---

## 7. a6600 vs a6700 (comparison only)

| Item | a6600 (av-cam 16,825,940 B) | a6700 (av-cam 13,805,416 B) |
|---|---|---|
| `IMAGE ASPECT` list | 16:9, 4:3, 15:9 (`VALUEID_MOVIE_ASP_*`) | Still/crop aspect enum 1:1, 16:9, 3:2, 4:3; `CROP_ASPECT_2_3/3_2/3_4/4_3/9_16` |
| Aspect debug string | `stl_aspect` param check only | `[CAM_MP]: ... stl_aspect:%d (0:16_9 1:4_3 2:3_2 3:1_1 4:17_9)` at 0x4300C6 |
| Movie aspect menus | `MOVIE_ASPECT_RATIO` (16:9/4:3/15:9) | `extern_menu_movie_rec_aspect_xavc` + `REC_MOVIE_ASPECT_RATIO_NOT_16_9` |
| 1620×1080 / 3240×2160 / 2880×2160 | present (still/Dual-Rec table) | **absent** |
| 1920×1280 / 1920×1440 | absent from av-cam | absent from av-cam |
| Open-gate strings | none | none |
| Video format names | up to 4096×2160, all 16:9/17:9 | up to 4096×2160, incl. 120p; all 16:9/17:9 |

The a6700 has a richer **still/crop** aspect enum (3:2, 1:1, 17:9) and explicit “movie aspect not 16:9” UI states, i.e. it is architecturally closer to offering a non-16:9 movie mode. It still has **no 3:2/4:3 video frame identifiers and no open-gate strings**. This is consistent with the public fact that open gate is an FX-series feature, not an a6x00 one.

No a6700 data is proposed for flashing.

---

## 8. Verdict

**Is a 1920×1280-class open-gate mode plausible from static evidence? — No, not as a configuration change.**

Proven:

1. Every movie frame the a6600 can produce is 16:9 (3840×2160 / 1920×1080 / 1280×720 / 640×360 / 480×270 / 800×480; AVCHD 1440×1080 is 16:9 storage with 4:3 pixel aspect).
2. `1920×1280` and `1920×1440` exist in the firmware **only as still-image sizes** in the generic aspect/size tables (3:2 and 4:3 lists), never in `av-cam.bin`, never in a movie format name, never in the UI movie placeholders.
3. The only 3:2/4:3 dimensions in the capture path keep the 16:9 height (1620×1080, 3240×2160, 1440×1080, 2880×2160) — i.e. horizontal crops of a 16:9 frame, not taller frames.
4. The movie aspect enum has **no 3:2 value at all** (16:9 / 4:3 / 15:9 only), and movie height is a quantised `PICT_SIZE` class (720 / 1080 / 2160).
5. There is no “open gate”/“OpenGate” string anywhere in the a6600 or a6700 trees, and none in `a6600_fdat.bin`.

Inferred / speculation:

6. The IMX284 sensor can physically deliver a 3:2 area (6000×4000 is used for stills), so a 3:2 *window* is electrically plausible; whether it can be read at video rates with the required line count is not determined statically.
7. The AVC/HEVC encoder is parametric and 4K-capable, so 1920×1280 (120×80 MB) is inside its envelope; the codec is very likely **not** the blocker.

What would have to change (minimum):

* New movie aspect id 3:2 in MPR/libObj (`PARAMID_MOVIE_ASPECT_RATIO`, `VALUEID_MOVIE_ASP_*`) and in the `LiroSeq` parameter checks (`mov_aspect_req`).
* New movie height class (e.g. 1280) in `PICT_SIZE_*` / `V_PICT_SIZE_*`, plus every switch on those enums (record-size validator, remaining-capacity, SPS/level, proxy, thumbnail, playback).
* New entries in the image-size tables (`xmax_tgt` derivation, `CaptureUtilityImageSize/JpegSize`) and in `libmprctrl`/`viewUnified2` tables.
* New UI resources (`.uxc`) and menu strings.
* A sensor readout mode with a 3:2 window at the target fps and matching `Astra` PRC / crop / resize configuration.
* Container/metadata: pixel aspect, coded size, level, and playback/thumbnail paths.

That is a cross-cutting feature addition, not a flag flip. Doing it without Sony’s per-model capability data, source, and toolchain is high-risk; a wrong SPS/level or buffer size can brick recording or corrupt clips.

**Confidence:** High (≈90 %) that no existing 3:2/4:3 open-gate video mode exists in this firmware. Medium (≈60 %) on the exact set of binary gates, because the final permission decision is a runtime capability-ID table stored in encrypted model data. Low confidence on any claim about sensor readout at video rates.

---

## 9. Negative results (searched, not found)

* `open gate`, `OpenGate`, `OPENGATE`, `open-gate` — 0 hits in `out/rootfs`, `out/usr`, `out/system`, `out/firmware`, `a6600_fdat.bin`, and the a6700 trees.
* `1920x1280` / `1920x1440` in `av-cam.bin` — 0 hits (u16 and u32 adjacent pairs).
* Any movie picture-size enum besides VGA / WVGA / 720 / 1080 / 2160 — none.
* Any movie aspect enum value `3:2` — none (still-image `3:2` exists: `VALUEID_STILL_ASP_3_2`, `VALUEID_EXPAND_FOCUS_ASP_3_2`, `STILL_FORMAT_ASPECT_3_2`).
* Video format names with width 1620 / 2880 / 3240 or height 1280 / 1440 / 2832 — none.
* Explicit encoder max width/height, `MaxFS`, macroblock-count or `level_idc` constants in `vcd_firmware.bin`, `codec_drv.ko`, `sa_avce_*`, `av-cam.bin` — none.
* Sensor readout/binning table with 3:2 dimensions (4240×2832, 2120×1416, 3000×2000, 6000×4000 at video rates) — none.
* 3:2 video identifiers in the a6700 that the a6600 lacks — none (the a6700’s 3:2 values are still/crop aspects).
* Movie/encoder modules in `a6600_updater.img` — none (updater-only ELFs and shell scripts).
* `dcv_psf_table_movie*.bin` do not contain frame dimensions (PSF/shading tables, headers `IMX210`/`IMX094`, 144 × 74-byte signed entries).

---

### Artifacts produced

Shipped in this repo:

* `docs/open-gate-analysis.md` (this file)
* `research/scripts/scan_dims.py` — u16/u32 adjacent dimension-pair scanner
* `research/data/dims_a6600.tsv` — 1408 dimension-pair hits with file/offset
* `research/data/hex_avcam_834b10.txt` — hexdump of the capture-size table
* `research/data/updater_strings.txt` — all strings from the updater image

Regenerated locally (not in the repo):

* `avcam.elf` — `research/scripts/mkelf.py`
* `avcam.dis` (225 MB) — `llvm-objdump --triple=thumbv7-linux-gnueabihf -d avcam.elf`
* `picrefs2.json` — `research/scripts/xref_pic2.py`

---

# Follow-up: 4:3 movie aspect verification

Scope: read-only. New method used here — `av-cam.bin` is a raw 0-based image (header `0a0000ea 4f52494c` = ARM `b`, magic `ORIL`; link base `0x635C6000`, verified because header entry `0x635C6044` resolves to a valid Thumb `push {r4-r11,lr}` at file offset `0x44`). It was wrapped in a synthetic ELF32 (`research/scripts/mkelf.py` → `avcam.elf`) and disassembled with `llvm-objdump --triple=thumbv7-linux-gnueabihf`. PIC references were recovered by decoding `ldr Rt,[pc,#imm]` + `add Rt, pc` pairs (`xref_pic2.py`, 110,719 refs → `picrefs2.json`); a literal is resolved as `target = u32(pool) + addr(add) + 4`.

## F1. Are `VALUEID_MOVIE_ASP_4_3` / `_15_9` selectable movie parameters, or pixel-aspect metadata?

**Answer: metadata / display-aspect descriptors. There is no selectable 4:3 movie mode on the a6600.**

Evidence (all proven by direct read):

| Item | Location | Content |
|---|---|---|
| `VALUEID_MOVIE_ASP_16_9` | `libObj.so` 0x1096B82 | string only |
| `VALUEID_MOVIE_ASP_4_3` | `libObj.so` 0x1096B99 | string only |
| `VALUEID_MOVIE_ASP_15_9` / `_PROXY` | `libObj.so` 0x109EB5B / 0x109EC00 | strings only |
| `pixelAspectRatio = [16:9]` | `libmpr.so` 0x965A6F |  |
| `pixelAspectRatio = [15:9]` | `libmpr.so` 0x965A89 |  |
| `pixelAspectRatio = [4:3]` | `libmpr.so` 0x965AA3 |  |
| `Normal( 4:3 )` / `Wide( 16:9 )` / `HFR( 15:9 )` | `libmpr.so` 0xB2E2CF / 0xB2E2DD / 0xB2E2EA | AVCHD display-aspect labels |

* Each aspect VALUEID string has **exactly one pointer reference in the whole 20.9 MB `libObj.so`**: the shared VALUEID→name array at `libObj.so` 0x13156A0 (3,220 entries, run 0x13156A0–0x13188F0). `_16_9` → index 23 (0x13156FC), `_4_3` → index 24 (0x1315700), `_15_9` → index 1231 (0x13169DC), `_15_9_PROXY` → index 1238 (0x13169F8). No descriptor table and no code points at these strings.
* That dictionary is not a capability list: it also contains values for hardware the a6600 does not have (proxy/`_PROXY` variants, `VALUEID_MOVIE_HSIZE_3840`, 240/200p rates). Dictionary membership therefore says nothing about availability.
* The three aspect values line up 1:1 with the three AVCHD/MPEG-2 display-aspect descriptors in `libmpr.so` (`Normal( 4:3 )`, `Wide( 16:9 )`, `HFR( 15:9 )` + the `pixelAspectRatio = [...]` variants). They describe how the stored frame is to be *displayed*, i.e. metadata written into the stream.
* No 4:3 movie geometry exists to back a 4:3 record mode: 0 hits for `960x720` and `1280x960` in the entire a6600 tree (`dims_a6600.tsv`), and no frame height of 960/1440 in any format table.

## F2. Do `mov_aspect_req` / `mov_size_req` / `mov_sizeh_req` accept any height besides 720/1080/2160?

**Answer: no. Heights are not compared at all — the validators only compare enum bytes. The only heights that exist as movie sizes anywhere in the image are 720 / 1080 / 2160 (+ SD 480, + proxy 270/360).**

Exact dispatch sites (proven):

1. The three `..._req` messages are *log names*, not comparisons. `av-cam.bin` 0x62A2CE–0x62A328 compares four request fields against single bytes of a saved backup and prints the name from the string at 0x9D6F7D (`mov_size_req`), 0x9D6FB6 (`frate_req`), 0x9D6FEC (`mov_aspect_req`), 0x9D7027 (`mov_sizeh_req`):
   `ldr r2,[r5,#0x24]; ldrb r3,[r4,#8]; cmp r2,r3` … `ldr r2,[r5,#0x28] vs [r4,#9]` … `[r5,#0x30] vs [r4,#0xa]` … `[r5,#0x34] vs [r4,#0xd]`. All four are `cmp`-against-enum-byte; there is no arithmetic on pixel heights (consistent with `FW: LiroSeq ParamCheckErr@%s[...] cur:%d req:%d`).
2. The only hard bounds on the movie aspect/size enums are small-index checks with a hard-coded maximum:
   * `av-cam.bin` 0x331362 `cmp r2,#0x3` / `bhi` → aspect index must be 0…3, else `FW: %s Invalid Aspect %d` (0x9691FC).
   * `av-cam.bin` 0x331380 `cmp r6,#0x3` / `bhi` → size index must be 0…3.
   * `av-cam.bin` 0x3314BC–0x3314C4 `cmp r5,#0x1` / `cmp r5,#0x2` / `cbz` → size index 0…2 for the dest-size lookup.
   * the 4 aspect values are then collapsed by a `tbb` jump table at 0x331366 into **2** geometry classes (aspect 0/1 → class 0, aspect 2/3 → class 1).
3. The record-size struct itself carries concrete pixels — `u16 w` at +0x20, `u16 h` at +0x22, `u8 size_type` at +0x2E (loaded at `av-cam.bin` 0x14AA60–0x14AA6A and used to index the 24-byte capture table at 0x834B14 via `mla r3, r2=0x18, r0, base`) — but the only validation applied to them is non-zero: `av-cam.bin` 0x331EB0–0x331ED4 `ldrh r2,[r4,#0x22]; ldrh r3,[r4,#0x24]; strh …; cbz/cbnz` → `FW: [%s] Invalid record size(%u, %u). Check image size backup value. cap mode: %u, aspect: %u, size type: %u` (0x9694EB). "aspect: %u, size type: %u" confirms both are enums.
4. The height universe of the whole image, from the movie format-name table (`av-cam.bin` 0x904F00–0x906200, 39 names):
   * widths = {480, 640, 800, 1280, 1440, 1920, 2048, 3840, 4096}
   * heights = **{270, 360, 480, 720, 1080, 2160}**
   * Full-rate record heights are therefore 720 / 1080 / 2160 only; 480 is SD, 270/360 are proxies. **1440 appears only as a width; 960 and 1280 never appear as a height.** The 24-byte capture table at `av-cam.bin` 0x834B14 agrees: 640x480, 1920x1080, 1440x1080, 1620x1080, 3840x2160, 2880x2160, 3240x2160.

## F3. Any encoder/record path for 1440x1080, 960x720, or another taller-than-16:9 frame?

**Answer: 1440x1080 exists, but only as an anamorphic 16:9 (AVCHD) grid. 960x720 does not exist anywhere. No taller-than-16:9 frame reaches the movie encoder on a6600.**

* `1440X1080_59_94I_50I` (`av-cam.bin` 0x905396), `1440X1080_23_98P`, `1440X1080_29_97P_25P`; capture-table entry 1440x1080 with stride **1472** (`av-cam.bin` 0x834B14) — 1440x1080 is the storage grid, 1472 is a padded stride. It is displayed as 16:9 (`Wide( 16:9 )`, `pixelAspectRatio = [4:3]` → 4:3 pixels over a 16:9 field of view). 1440-wide interlaced formats are the AVCHD set of the shared multi-model image, not an a6600-recorded format (a6600 records XAVC S: 1280x720 / 1920x1080 / 3840x2160).
* `960x720`: 0 hits in `dims_a6600.tsv` and 0 hits in the format-name table. Not present in any form.
* Taller-than-16:9 frames that *do* exist in the shared image, and why they are not movie modes: `640x480` (4:3, names `640X480_30_25P`/`640X480_60_50P` at `av-cam.bin` ~0x905xxx; legacy SD entries, no a6600 UI mode), `1920x1280` (3:2) and `1920x1440` (4:3) at `libmprctrl.so` 0x26974 / 0x26C20 — those are **still-image** size lists (`libmprctrl.so` 0x26924–0x26B4C is grouped by still aspect: 3:2 / 16:9 / 4:3), and `libObj.so` UI placeholders `<1280>28M 120p`, `<1280>50M 120p`, `<1920>50M 24p/30p/60p`, `<3840>60M 24p/30p` contain only 1280/1920/3840 widths, i.e. 16:9 only.
* Dual-Rec / still JPEG handlers were kept separate from the movie path: they are reached through the still-image size tables above and never through the `0x834B14` capture table / record-size struct (`+0x20/+0x22/+0x2E`) described in F2.

**Net conclusion:** the 4:3/15:9 movie aspect VALUEIDs are AVCHD pixel-aspect metadata, the movie size validators never compare pixel heights (only enum bytes with hard-coded 0…3 / 0…2 bounds), and no 960x720 or 3:2/4:3 movie geometry exists. **No taller-than-16:9 video mode is reachable on stock firmware.**

New artifacts: `mkelf.py`, `avcam.elf`, `avcam.dis` (225 MB Thumb-2 disassembly), `rng.py` (address-range extractor), `xref_pic2.py`, `picrefs2.json`, `recon_avcam.py`, `find_selfrel.py`, `find_strtab.py`.
