# Movie patch map — 1920×1280 3:2 24p (a6600 v1.10)

Status: **partial — test-only route byte-confirmed; per-slot producer unresolved.**
The encoder size comes from `MPR::VResolution`, not from the av-cam record; no
1920×1280 code exists. A global `GetPictureSize` edit can prove the pipeline; a
proper per-slot feature needs the `ctx+0x3a8` writer. The movie VALUEID namespace
has no 3:2, but aspect does not gate geometry. Level source is profile metadata,
not resolution-keyed. No patched image has been written; no camera write has been
attempted.

Target assumed: 1920×1280, AVC 8-bit 4:2:0, 24p, by repurposing one 1080 record.
All offsets are file offsets in `out/system/av-cam.bin` (16,825,940 bytes).

Confidence labels: **Confirmed** = read from the binary/code; **Inferred** =
follows from the data but not proven; **Unknown** = not resolved.

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
| `+0x0C` | u32 | **rate key** used to match camera state (`+0x704`), not a setter | Confirmed |
| `+0x10` | u32 | 1 = half-height (540) variant, 0 = full | Inferred |
| `+0x14` | u32 | 13 / 15 / 12 per class | Unknown |
| `+0x18` | u32 | record id (`0x321` … `0x33F`) | Confirmed |
| `+0x24/+0x30/+0x38` | u32 | 125000 or 87500 (repeated) | Inferred |
| `+0x34` | u32 | height+8 (1088 / 597) | Inferred |
| `+0x48` | u32 | packed canvas, same encoding as `+0x04` | Inferred |
| `+0x50` | u32 | 3072/3328, not width-derived | Unknown |

The selector matches five keys (w/h, `+0x0C`, scan, `+0x14`) against camera state
and skips the aspect compare while `+0x08` is wildcard (`0x41B2F6–0x41B378`).
This is **not** the `0x834B14` capture grid and not the `0x904F00–0x906200` name
lookup.

## 2. 1080-class AVC progressive records

All have `h=1080`, `+0x10=0`, `+0x08=0xFFFFFFFF`:

| id | entry | w×h | class | rate key `+0x0C` |
|---|---|---|---|---|
| 801 | `0x879960` | 1920×1080 | 6 | 2 |
| 802 | `0x8799B4` | 1920×1080 | 6 | 5 |
| 809 | `0x879AB0` | 1920×1080 | 7 | 2 |
| 810 | `0x879B04` | 1920×1080 | 7 | 5 |
| **822** | `0x879C54` | 1920×1080 | 6 | 3 |
| 828 | `0x879D50` | 1920×1080 | 7 | 3 |

**Candidate: id 822 @ `0x879C54`** — the existing 24p HD entry. 801 and 822 differ
only at `+0x0C` (2 vs 3), so editing 801's key to 3 makes it duplicate 822 and
shadows it. Do not edit the rate key.

## 3. Known byte changes for 822 (not applied)

| Offset | Current | Proposed | Reason | Confidence |
|---|---|---|---|---|
| `0x879C58` | `80 07 38 04` (1920×1080) | `80 07 00 05` (1920×1280) | packed w/h | field Confirmed, value Inferred |
| `0x879C9C` | `80 07 38 04` (1920×1080) | `80 07 00 05` (1920×1280) | canvas/valid size | Inferred |
| `0x879C88` | `40 04 00 00` (1088) | `08 05 00 00` (1288) | height+8 alignment | Inferred |
| `0x879C5C` | `ff ff ff ff` | leave wildcard | selector ignores aspect while wildcard | Confirmed |

Do **not** change `0x879C60` (`+0x0C = 3`): it is the 24p match key.

## 4. Why the patch is not complete

1. **Aspect is a real gate.** The movie VALUEID namespace has only 16:9, 4:3 and
   15:9 (+proxy); there is no `VALUEID_MOVIE_ASP_3_2`. The 3:2 string found earlier
   is in the DefStruct dump namespace (`MOVIE_ASPECT_3_2`), not the selectable
   VALUEIDs. `FeaCore::SetRecAspect` (`0x531051`, `tst.w r2,#0x2b` at `0x5310D0`)
   accepts codes `{0,1,3,5}` and rejects 2. A selectable 3:2 mode needs a new
   VALUEID, a mask bit, and downstream support.
2. **Size representation is a real gate.** `libObj`'s `FMTsize` is
   `{HD1080, HD720, SD, VGA, WVGA, 4K_216}` (`0x1050827`); no 1920×1280 member
   exists in these enums. `FeaCore::SetRecDefinition` (`0x5310DC`) takes a size
   code `0..0xC` plus ≤4 codec pairs (`0x5310FC` is a pair count); the code is
   stored raw into the codec block. A new size code and its mapping to width/height
   must be added.
3. **Request path.** The movie request carries size/sizeh/frate bytes (`+8/+9/+0x0D`)
   validated against saved state (`0x62A2E8–0x62A2FA`). A record edit alone does not
   change what the UI/param layer requests, so the request site must agree.
4. **Level.** 1920×1280 = 9600 macroblocks; Level 4.2 MaxFS is 8704 and 5.0 is
   22080. The codec blobs (`usr/codec/*_firmware.bin`) show AVC encoder strings but
   no observable `level`/`level_idc` table. **Unknown**; Level 5.0 is only a spec
   inference.
5. **Install.** G0 is unproven (`docs/install-path.md`): container rebuild is
   solved, acceptance is not.

`libmprctrl.so` has a native 3:2 still-size family at `0x26974` (`1920,1280`,
`2048,1360`, `2128,1416`); it does not make it a movie mode.

## 4.1 Encoder size source (M1 result)

The encoder width/height do **not** come from the av-cam record; they come from
`MPR::VResolution` via `MprLibCore::GetPictureSize` (`libmpr 0x87FDD4`, TBB table
`0x87FDE2`, 13 entries):

| code | size | code | size |
|---|---|---|---|
| 0 | 1280×720 | 7 | 640×480 |
| 1 | 1440×1080 | 8 | 800×480 |
| 2 | 1920×1080 | 9 | 640×360 |
| 3 | 3840×2160 | 10/11 | unsupported |
| 4 | unsupported | 12 | 480×270 |
| 5 | 720×480 | | |
| 6 | 720×576 | | |

There is no 1920×1280 entry. `FeaCore::SetRecDefinition` stores the code at
`block+codec*0x108+0x1668`; `RecStart`/`EncStart`/`EncOpen` pass it to
`GetPictureSize`.

The size code is stored per slot in a settable struct, not hardcoded per FMTsize:
`MprIf::SetRecDefinition` (`libmpr 0x8a5990`) → `FeaIf` (`0x54a7b0`) →
`FeaCore` (`0x5310dc`) copies an 8-byte `{VCodec, VResolution}` entry from the
array at `ctx+0x3a8` (libObj send site `0x8f614a`, caller `0x905dec`). Codes
4/10/11/12 pass the `cmp #0xC` check and are stored; they fail only later in
`GetPictureSize`. The **writer** of `ctx+0x3a8` (the real movie-format → code
mapping) was not found; it is an indirect store, likely from the recorder param
block or a message payload. No `{2,0,5,7,8,3}` table exists in libObj/libmpr.

Byte confirmation: `0x87fe08: 4f f4 87 63` = `mov.w r3,#0x438` (1080). The
single-byte change `0x87FE0A: 0x87 → 0xA0` gives `0x63a0` = 1280. Caveat: case 1
(1440×1080) branches to `0x87fe06` and falls through, so this also changes
1440×1080 to 1280 high. A code-2-only change needs the TBB byte at `0x87fde4`
(`0x10`) retargeted into a code cave.

Two routes:

- **Test-only (smallest):** the `0x87FE0A` edit plus record 822 geometry. Proves
  the pipeline; 1440×1080 becomes 1440×1280 if that mode is selected.
- **Proper:** repurpose code 4 (currently unsupported; TBB entry `0x87FDE6` is
  `0x3C`) or code 12 (480×270, case at `0x87FE4A/0x87FE50`), preserving 1080p.
  A new code `0xD` needs both `cmp #0xC` checks (`0x87FDDA`, `0x531154`) and a
  larger TBB.

Either route still needs the `ctx+0x3a8` producer and record 822's
`+0x04/+0x34/+0x48` to match the new geometry.

## 4.2 Aspect (M2 result)

Aspect does **not** drive geometry. `block+0x1664` is read only by a codec-status
helper and debug logging. The encoder gets one metadata byte from
`GetPictureAspectForCodecDrv` (`0x87FD00`, maps 0→2, 1→3, else→0). A 1920×1280
frame with the existing 16:9 code produces a 1920×1280 stream tagged 16:9 (wrong
DAR), but no geometry rejection was found. A first recording test does **not**
need a 3:2 VALUEID; correct DAR does.

## 4.3 H.264 level (M3 result)

`libmpr` has a profile/level source at `0xb162f8` (`ProfileInfo->avcProfileLevel`)
with enum strings `AVC_PROFILE_LEVEL_MAIN_21 … HIGH_52`, and an SPS dump of
`m_AVCLevelIndication` (`0xb19740`, values `0x1E`=3.0, `0x28`=4.0, `0x2A`=4.2).
The closed codec blobs (`usr/codec/*_firmware.bin`) contain no level, MaxFS or
MaxMBPS table. No resolution-keyed level table was observed; level appears to come
from XAVC profile/clip metadata into the SPS. **Unknown**, not predicted.

## 5. Corrections to earlier notes (audit)

- **Wrong:** "3:2 exists in the movie aspect enum". The VALUEIDs are 16:9/4:3/15:9
  only; 3:2 exists only in the DefStruct dump namespace.
- **Wrong:** "aspect is not a recording blocker". `0x2B` rejects code 2; a
  selectable 3:2 mode needs a new VALUEID and mask bit.
- **Wrong:** "change slot 801 rate 2 → 3 for 24p". `+0x0C` is a match key; the edit
  duplicates record 822 and shadows the existing 24p entry. Candidate is 822, key
  unchanged.
- **Corrected earlier:** `CnvMovieAspect` = `0x239D1`, table `0x376EC =
  [3,1,4,2,0]`; `0x376F8` is element 3 of the same array. Still twin
  `CnvStillAspect` uses `0x37920`.
- **Corrected earlier:** `0x834B14` is the capture grid, not the record table;
  the `0x62A288–0x62A33E` block compares state vs request and aborts.
- "Encoder accepts arbitrary w/h/canvas" came from log/param strings; the encoder
  SPS/level logic is in closed blobs and was not observed.

## 6. Remaining mapping work

1. **M1 — size plumbing: partial.** The code is a per-slot field forwarded from
   `ctx+0x3a8`; codes 4/12 are already accepted. Remaining: the writer of
   `ctx+0x3a8`. Only after that is a per-slot (non-global) edit definable.
2. **M2 — aspect necessity: answered.** Not needed for a first recording test;
   only for correct DAR.
3. **M3 — level: answered as Unknown.** Level comes from profile metadata, not a
   resolution table; the codec blobs expose nothing. Level 5.0 remains a spec
   inference only.
4. **M4 — build:** the test-only route is now byte-confirmed. A dry-run diff can
   be produced, but it changes 1440×1080 too and proves the pipeline rather than
   delivering the feature. The proper route waits on `ctx+0x3a8`.

Only after the `ctx+0x3a8` writer is resolved is the per-slot patch a candidate
rather than a guess, and only after G0 acceptance is a flashable image worth
building.
