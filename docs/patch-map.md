# Movie patch map — 1920×1280 3:2 24p (a6600 v1.10)

Status: **partial, not implementable yet.** One movie record is identified and its
width/height bytes are known, but the 3:2 aspect path and the H.264 level path are
unsolved. No patched image has been written; no camera write has been attempted.

Target assumed for this pass: 1920×1280, AVC 8-bit 4:2:0, 24p, by repurposing one
existing 1080 slot (Option A). All offsets are file offsets in `out/system/av-cam.bin`
(16,825,940 bytes).

Confidence labels: **Confirmed** = read from the binary/code; **Inferred** = follows
from the data but not proven; **Unknown** = not resolved.

## 1. The movie record table

| Item | Value | Confidence |
|---|---|---|
| Table base | `0x87990C` | Confirmed |
| Entry stride | `0x54` (84) — `movs r2,#0x54; mla` at `0x41B36E` | Confirmed |
| Entries | 16, then a zero terminator at `0x879E4C` | Confirmed |
| Separate 4K table | starts `0x879EA0` | Confirmed |
| Record reader | `0x41B2EA–0x41B356` | Confirmed |

Fields inside a record:

| Off | Type | Meaning | Confidence |
|---|---|---|---|
| `+0x00` | u32 | class (6 = 125000 group, 7 = 87500, 14/22 = 4K) | Inferred |
| `+0x04` | u32 | packed `w \| h<<16` | Confirmed |
| `+0x08` | u32 | aspect id, `0xFFFFFFFF` = wildcard | Confirmed |
| `+0x0C` | u32 | rate/quality code (0,1,2,3,5) | Inferred |
| `+0x10` | u32 | 1 = half-height (540) variant, 0 = full | Inferred |
| `+0x14` | u32 | 13 / 15 / 12 per class | Unknown |
| `+0x18` | u32 | record id (`0x321` … `0x33F`) | Confirmed |
| `+0x24/+0x30/+0x38` | u32 | 125000 or 87500 (repeated) | Inferred |
| `+0x34` | u32 | height+8 (1088 / 597) | Inferred |
| `+0x48` | u32 | packed canvas, same encoding as `+0x04` | Inferred |
| `+0x50` | u32 | 3072/3328, not width-derived | Unknown |

This is **not** the same table as `0x834B14` (the 7×24-byte capture grid) and not the
format-name lookup at `0x904F00–0x906200` (46 names, dispatched by `tbh` at `0x97576`).
Aspect is absent from this record table (wildcard).

## 2. 1080-class AVC progressive records

All have `h=1080`, `+0x10=0`, `+0x08=0xFFFFFFFF`:

| id | entry | w×h | class | code `+0x0C` |
|---|---|---|---|---|
| **801** | `0x879960` | 1920×1080 | 6 | 2 |
| 802 | `0x8799B4` | 1920×1080 | 6 | 5 |
| 809 | `0x879AB0` | 1920×1080 | 7 | 2 |
| 810 | `0x879B04` | 1920×1080 | 7 | 5 |
| 822 | `0x879C54` | 1920×1080 | 6 | 3 |
| 828 | `0x879D50` | 1920×1080 | 7 | 3 |

Candidate: **id 801 @ `0x879960`** — already 1920 wide, progressive, aspect wildcard,
lowest 1080 id.

## 3. Known byte changes (not applied)

| Offset | Current | Proposed | Reason | Confidence |
|---|---|---|---|---|
| `0x879964` | `80 07 38 04` (1920×1080) | `80 07 00 05` (1920×1280) | packed w/h | field Confirmed, value Inferred |
| `0x8799A8` | `80 07 38 04` (1920×1080) | `80 07 00 05` (1920×1280) | canvas/valid size | Inferred |
| `0x879994` | `40 04 00 00` (1088) | `08 05 00 00` (1288) | height+8 alignment | Inferred |
| `0x879968` | `ff ff ff ff` | leave wildcard | 3:2 id not resolved | Unknown |
| `0x87996C` | `02 00 00 00` | only if code 2 ≠ 24p | 24p code unidentified | Unknown |
| `0x8799B0` | `00 0c 00 00` (3072) | unchanged | unit unknown | Unknown |

## 4. Why this is not a patch yet

1. **Aspect.** The record table uses a wildcard, but the aspect enum is a 5-value map
   (`UtilStillSize::CnvMovieAspect`, `libmprctrl.so` `0x239D1`, table `0x376F8` =
   `[2,0,3,4,1]`, default 1). There is **no 3:2 value**. Whether the aspect id is only
   metadata (and `w/h` alone produce a 3:2 stream) is unproven.
2. **Rate.** The `+0x0C` code for 24p is not identified, so "24p" is still an assumption.
3. **Level.** 1920×1280 = 9600 macroblocks. Level 4.2 MaxFS is 8704 and Level 5.0 is
   22080, so a 1080 slot's level cannot signal 1280. The encoder is in closed blobs
   (`usr/codec/*_firmware.bin`) and the SPS/level derivation is **Unknown**. This is a
   spec inference, not observed in the camera binaries.
4. **Request path.** `0x62A288–0x62A33E` compares the saved state against the request
   (`mov_size_req` `0x9D6F7D`, `frate_req` `0x9D6FB6`, `mov_aspect_req` `0x9D6FEC`,
   `mov_sizeh_req` `0x9D7027`) and aborts on mismatch. It is not a pixel ceiling, but
   the caller (UI/param layer) must request the new geometry too, or the sequence
   aborts. Where that request gets its size for slot 801 is not mapped.
5. **Install.** G0 is unresolved (`docs/install-path.md`). Even a perfect patch has no
   verified install path.

`libmprctrl.so` already contains a native 3:2 still-size family at `0x26974`
(`1920,1280`, `2048,1360`, `2128,1416`, stride 12), which is why the geometry is
plausible; it does not make it a movie mode.

## 5. Corrections to earlier notes

- Earlier summaries called `0x62A2CE–0x62A328` "validators" with range semantics.
  They compare state vs request and abort; the exact range is `0x62A288–0x62A33E`.
  They do not enforce a 1080 ceiling.
- `0x834B14` is the capture-size grid (7 entries × 24 bytes), **not** the movie format
  record table. The record table is `0x87990C`.
- "Encoder accepts arbitrary w/h/canvas" came from parameter/log strings. The
  encoder's SPS and level logic is in closed blobs and was not observed.
- "1920×1280 requires Level 5.0" is an H.264 spec inference, not a binary finding.

## 6. Remaining mapping work

1. Resolve the aspect request: is 3:2 carried, or is `1920×1280` with SAR 1:1 enough?
2. Identify the `+0x0C` rate code for 24p and 30p.
3. Find the encode-time level source, or capture an SPS from a known 1080 clip.
4. Trace slot 801's request path from the UI/param layer to the record table.

Only after 1–4 is the patch a candidate rather than a guess, and only after G0 is a
flashable image worth building.
