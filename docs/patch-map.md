# Movie patch map — 1920×1280 3:2 24p (a6600 v1.10)

Status: **partial — geometry/rate definable, request path and level unresolved.**
Slot 801's width/height and rate bytes are known, and the 3:2 aspect enum exists.
The remaining blocker is the request/size representation outside `av-cam`. No
patched image has been written; no camera write has been attempted.

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
| `0x879968` | `ff ff ff ff` | leave wildcard | aspect not used by the selector | Confirmed |
| `0x87996C` | `02 00 00 00` | `03 00 00 00` | rate code 3 = 24P (libObj enum) | enum Confirmed, field mapping Inferred |
| `0x8799B0` | `00 0c 00 00` (3072) | unchanged | unit unknown | Unknown |

## 4. Why this is still not a complete patch

1. **Aspect is not a recording blocker.** All 16 records use aspect wildcard, and the
   selector at `0x41B33A` skips the aspect compare when wildcard (Confirmed). The
   aspect enum already contains 3:2: 0-based `{0:16:9, 1:4:3, 2:3:2, 3:15:9}`
   (`libObj` strings `0x10508CC`, `0x10506A3`), 1-based DefStruct `{1:4:3, 2:16:9,
   3:3:2, 4:1:1, 5:17:9}` (`0x10310F4`). If the UI must *select* 3:2,
   `FeaCore::SetRecAspect` (`libmpr 0x531050`) masks with `0x2B` at `0x5310D0`,
   which rejects a 0-based 3:2 value; that would need `0x2B → 0x2F` (Inferred).
2. **Rate.** The libObj enum is `0:60P 1:60I 2:30P 3:24P 4:120P 5:240P`
   (`0x1050621`, `0x105087F`), so 24p = 3. Whether record `+0x0C` uses the same enum
   is Inferred; the selector compares it to camera state `+0x704`.
3. **Request path — the real blocker.** Changing the table alone is not enough. The
   request carries size/sizeh/frate bytes (`+8/+9/+0x0D`) that are validated against
   saved state (`0x62A2E8–0x62A2FA`). `libObj`'s `FMTsize` is
   `{HD1080, HD720, SD, VGA, WVGA, 4K_216}` (`0x1050827`) and `FeaCore::SetRecDefinition`
   (`0x5310DC`) validates a size index ≤4 and value ≤0xC — there is no 1920×1280
   representation. A libObj size/slot site must change too.
4. **Level.** 1920×1280 = 9600 macroblocks; Level 4.2 MaxFS is 8704 and 5.0 is 22080.
   The codec blobs (`usr/codec/*_firmware.bin`) show AVC encoder strings but no
   `level`/`level_idc` table (Unknown). This is a spec inference, not observed.
5. **Install.** G0 is unproven (`docs/install-path.md`); the container rebuild is
   solved, acceptance is not.

`libmprctrl.so` has a native 3:2 still-size family at `0x26974` (`1920,1280`,
`2048,1360`, `2128,1416`), which is why the geometry is plausible; it does not make
it a movie mode.

## 5. Corrections to earlier notes

- `CnvMovieAspect` is `libmprctrl 0x239D0` with table **`0x376EC` = `[3,1,4,2,0]`**,
  not `0x376F8`; the earlier window was the same table shifted by `0xC`. It has no
  in-firmware caller (exported utility only).
- "No 3:2 aspect value exists" was **wrong**: 3:2 is in the libObj enums. The gate is
  the `0x2B` mask in `FeaCore::SetRecAspect`, not a missing value.
- Earlier summaries called `0x62A2CE–0x62A328` "validators" with range semantics.
  They compare state vs request and abort; the range is `0x62A288–0x62A33E`.
- `0x834B14` is the capture-size grid (7×24 bytes), **not** the movie record table.
  The record table is `0x87990C`.
- "Encoder accepts arbitrary w/h/canvas" came from parameter/log strings; the
  encoder's SPS/level logic is in closed blobs and was not observed.
- "1920×1280 requires Level 5.0" is an H.264 spec inference, not a binary finding.

## 6. Remaining mapping work

1. Find the `libObj` size/slot site that must represent 1920×1280 (the `FMTsize`
   enum and `SetRecDefinition` size index) and the request bytes it feeds.
2. Confirm record `+0x0C` uses the `RecFrameRate` enum (3 = 24P) and that slot 801's
   current `2` is 30P.
3. Find the encode-time level source, or capture an SPS from a known 1080 clip.
4. Decide whether the UI needs a selectable 3:2 label, or whether a repurposed 1080
   entry is enough.

Only after 1–3 is the patch a candidate rather than a guess, and only after G0
acceptance is a flashable image worth building.
