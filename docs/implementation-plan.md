# a6600 (ILCE-6600) open-gate 1080p — implementation plan

Date: 2026-11-03
Target: ILCE-6600, firmware **1.10** (`38114_02.2020071501`), ARMv7 / CXD90045
Scope: add a selectable **3:2** movie mode in the 1080 class (target 1920×1280,
24/30p, AVC 8-bit 4:2:0) on the user's own camera.
Status of evidence: Phase 0 (G0) investigated statically — G0 **unresolved,
fail-closed**. No hardware writes.

> **Review corrections (2026-11-20):**
> 1. The runtime preload route (`docs/preload-path.md`) changes only the
>    encoder-size query in `libmpr.so`. It does **not** change record 822 in
>    `av-cam.bin`, sensor readout or SPS. `og.so` alone is not a complete
>    open-gate test and must not be installed as one.
> 2. `av-cam.bin` contains **IMX284E** imager-driver symbols, but also
>    IMX210/IMX094 PSF headers, so it is shared across models and does not prove
>    the fitted part. External lists name IMX271AQR for the a6600. G1 is
>    "sensor readout", not "IMX284 readout".
> 3. `init` unconditionally *attempts* to launch `/bin/ash` on a console. An
>    interactive serial shell and file-level rollback are still unproven, so
>    recovery is conditional (`docs/uart-shell.md`).
> 4. 1920×1280 is 9,600 macroblocks, above H.264 Level 4.2 MaxFS 8,704, so a
>    compliant stream needs Level 5.0. Whether the encoder selects that level
>    is unknown; measure a stock clip's SPS before changing anything.
> 5. G2 for a preload-only experiment means a verified `/setting` backup plus a
>    demonstrated restore of the changed files. A full NAND restore test is
>    required before any partition/flash write, not before a runtime file test.

> **Phase 0 result, corrected (2026-11-03, pass 2):** the entire extractable
> update path is the normal OS: `im.elf → libIMDB → libupdaterufp → crypter →
> bodyimg(cramfs) → libupdaterbody → scripts`. It verifies **CRC32 only**; the
> 256-byte FDAT trailer is never read, and no RSA/DER/PEM key or verifier exists
> in 48 update-path files. `nflasha1`/`nflasha2` are mounted only to read
> model/region/version (`dat2/dat3/dat4`), not to verify. The earlier
> "signature blocks modified updates" claim was overstated; enforcement, if any,
> is in the loader/ROM. The PC tool also has no firmware verifier. Result: the
> install is plausibly open but unproven; still do not flash.
> Full evidence: repo `docs/install-path.md`; reproduce with
> `research/scripts/inspect_updater.py`.
>
> **G0 container proof (2026-11-03):** `research/scripts/fdat_roundtrip.py`
> rebuilds the DAT byte-for-byte (316,672,424 B, DEND CRC 0x157d2ed5) from the
> decrypted payload. Encryption is solved. Remaining G0 unknown: whether the
> 256-byte trailer is enforced (no visible verifier) and how to deliver a file
> (custom UFP sender or patched exe). Hardware acceptance is untested.
>
> **Phase 1 result (partial, audit-corrected):** the movie record table is
> `av-cam.bin 0x87990C` (stride 0x54, 16 entries); the 24p HD record is **822 @
> `0x879C54`**, not 801. `+0x0C` is a match key, not a setter — editing it
> duplicates and shadows 822. The movie VALUEID namespace has **no 3:2**
> (`FeaCore::SetRecAspect` `0x2B` mask rejects it), and `libObj`'s `FMTsize` has
> no 1920×1280. Option A alone is insufficient; a new VALUEID and size code are
> required. H.264 level remains unknown (closed encoder blobs). No patched image
> was written. See repo `docs/patch-map.md`.
>
> **M1/M2 result:** encoder w/h come from `MPR::VResolution` via
> `GetPictureSize` (`libmpr 0x87FDD4`, 13 codes, no 1920×1280). Test-only route:
> patch `0x87FE0A` (code 2 height, byte-confirmed `0x87→0xA0`) + record 822
> geometry; it also changes 1440×1080 to 1440×1280. Proper route: repurpose code 4
> (or 12) and make libObj request it — codes pass the `cmp #0xC` store, but the
> per-slot value comes from the `0x913854` format switch and its MWF msg
> `0x2005/0x1025` selector; the sender is unresolved. Aspect does
> not gate geometry; 16:9 metadata is wrong DAR but records. Level: no code or
> table found. `libmpr 0xb162f8`/`0xb19740` are `.rodata` log labels, not code;
> the chain ends at a virtual call (`0x54807c`, `r4=[r6+0x3cc]`). Codec blobs
> expose no level table → Unknown.
>
> **N1 result:** the VResolution value is chosen by switch helper `0x913854` from
> the per-slot format field `obj+0x184*slot+0x208`, emitting constants `0..9`
> (no `0xC`). The 24p 1080 path requests code 2; normal movie recording never
> emits code 12. The format field is fed by MWF msg `0x2005/0x1025`
> (`GetParam(0x2002)` at `0x90bf5c`). A per-slot edit needs a new switch case or
> a repurposed format code, plus the msg producer; there is no static data table.
> Audit also corrected: the fill buffer is stack-local (`libObj 0x904f84`), and
> `0xbb`/`0x3ed` are log arguments, not array metadata.

---

## 1. Goal and non-goals

**Goal:** a movie mode that records the full 3:2 sensor area at 1080-class
resolution, with correct SPS/container metadata, playable on the camera and
on a PC, and selectable from the movie menu.

**Minimum useful result:** 1920×1280 at 24p or 30p, AVC, one format slot.

**Stretch:** 1920×1440 (4:3), 25p/30p, HDMI output correct.

**Non-goals for this plan:**
- 4K open gate (sensor readout, thermal and encoder headroom unproven).
- HEVC, 10-bit, 4:2:2 (no encoder assets in the a6600 image).
- Changing still-photo behaviour.
- Distributing patched firmware or keys.

---

## 2. What is known (and how strong it is)

| Fact | Status | Evidence |
|---|---|---|
| Movie size is enum-quantised (`VGA/720/1080/2160`), not free w/h | Proven | `av-cam.bin` validators 0x62A2CE–0x62A328 |
| All 39 movie format names use heights 270/360/480/720/1080/2160 | Proven | `av-cam.bin` 0x904F00–0x906200 |
| Movie aspect enum is 16:9; 4:3/15:9 are AVCHD metadata only | Proven | `libObj.so` `VALUEID_MOVIE_ASP_*`; `libmpr.so` PAR strings |
| 1440×1080 is anamorphic 16:9, not a taller frame | Proven | format 0x905396, table 0x834B14 |
| 1920×1280/1440 exist only as still sizes | Proven | `libmprctrl.so` 0x26974 / 0x26C20 |
| Encoder accepts arbitrary w/h/canvas and is 4K-capable | Proven | codec open params ~0x90A370 |
| 1920×1280 needs H.264 **level 5.0** (9600 MBs > level 4.2 MaxFS 8192) | Inferred from spec | H.264 MaxFS table; encoder config still to inspect |
| Sensor can deliver 3:2 at still rates (6000×4000) | Proven (stills) | sensor size tables |
| Sensor can deliver 3:2 at 24/30 fps video rates | **Unknown** | no readout mode found in static data |
| Runtime gating uses capability-ID data in encrypted partitions | Inferred | `CapIdTblMgr`, `PARAMID_CAP_INFO_*` |
| FDAT wrapper ends in a 16-byte IV + 256-byte high-entropy trailer; `fwtool` decrypts Gen4 but cannot encrypt it | Observed | `inspect_updater.py`; `fwtool/sony/fdat.py` `AesCbcCrypter.encrypt` raises |
| Any unsigned persistent install path exists | **Unknown — the critical gate** | PC side ruled out; camera-side verifier not extracted |

---

## 3. Hard gates (stop if a gate fails)

**G0 — Install path.** There must be a *verified* way to run patched code or
write a modified partition, plus a tested restore. No signature verifier was
found in the extractable update path (CRC32 only), and the PC updater does not
verify the firmware. The remaining unknown is the 256-byte FDAT trailer and the
loader/ROM; the install is plausibly open but unproven. **If G0 fails, the project
stops at research.** No exceptions.

**G1 — Sensor readout.** The A6600 sensor must have a 3:2 binning/window mode
that runs at 24 or 30 fps with acceptable rolling shutter. Identify the actual
sensor part first. If the only 3:2 mode is the slow still readout, the plan stops.

**G2 — Recovery.** A complete partition dump and a *tested* restore on the same
unit, plus a second unit or a service option, before any write. Without this,
no hardware testing.

**G3 — Pipeline fit.** Memory, encoder level, muxer and thermal budget accept
1920×1280. This is the least likely to block, but is checked before patching.

---

## 4. Phase 0 — Baseline and recovery (1–3 days)

1. Freeze the exact input: updater hash, extracted trees, current camera state.
2. Map the boot chain from `out/rootfs`, `out/usr` and `out/firmware`:
   init scripts, mount points, which partition holds what, and what the
   bootloader verifies (rootfs, `/usr`, `av-cam`, config).
3. Read the updater verifier (`chkfirm.sh`, `bksb.elf`, `libupdaterbody.so`)
   and document the signature/version/guard checks. This defines G0.
4. Inventory service-mode and hardware options: PMCA service commands,
   test points, NAND/eMMC access, any documented restore procedure.
5. Produce `docs/install-path.md` with a decision: signed update, service mode,
   hardware write, runtime-only, or none.

**Deliverable:** a yes/no on G0 with evidence, and a recovery procedure draft.
**Abort:** no verified install/restore path → publish the research and stop.

---

## 5. Phase 1 — Map the movie pipeline (1–2 weeks)

Work from the extracted files with REA/rizin and the existing helper scripts.
Open `out/avcam.elf` (from `research/scripts/mkelf.py`) and the ARM ELFs.

### 5.1 av-cam validators and tables
- Fully disassemble 0x62A288–0x62A33E (`mov_aspect_req`, `mov_size_req`,
  `mov_sizeh_req`, `frate_req`) and name every field. These compare state vs
  request and abort; they are not range checks.
- Map the movie *record* table at `0x87990C` (stride `0x54`, 16 entries). The
  older `0x834B14` reference is the 7×24-byte capture grid, not this table.
- Find where the encoder is opened: `picture_width/height`, `canvas_size`,
  `valid_size`, level/profile, and the SPS writer.
- Resolve slot 822 (`0x879C54`) and trace its request path from the UI/param
  layer. Candidate bytes and open items: `docs/patch-map.md`.

### 5.2 UI and media layers
- `libObj.so`: movie aspect/size parameter IDs, menu labels, validators.
- `libmpr.so` / `libmprctrl.so`: `PICT_SIZE_*`, `MOVIE_FORMAT_TYPE_*`, format
  list, any aspect-dependent stride.
- Identify the smallest enum slot that can be repurposed without breaking
  another mode.

### 5.3 Sensor and timing
- Locate the sensor mode table in `av-cam.bin`: full 6000×4000, binning modes,
  line rates, exposure limits. First confirm which sensor part the A6600 uses.
- Determine whether a 3:2 window/binning mode exists at video rates (G1).
- Check memory stride/alignment: 1920 width and 1280 height are already
  macroblock-aligned, so no padding change is expected.

### 5.4 Container and SPS
- Find the SPS/PPS writer and the muxer's dimension source.
- Confirm SPS level/profile fields can be set to level 5.0 and that the muxer
  accepts a non-standard height.
- Check camera playback and HDMI path assumptions (display may letterbox).

**Deliverable:** `docs/patch-map.md` with exact file offsets, current bytes,
proposed bytes, and every call site that must agree.

---

## 6. Phase 2 — Choose the patch strategy (2–4 days)

**Option A (recommended first): repurpose one 1080 format slot.**
Keep the enum count and UI, change one format's stored dimensions/aspect/SPS
to 1920×1280 3:2. Smallest surface; proof of concept.
Risk: the changed table may be shared by several menu entries, and aspect
flags may be derived elsewhere. Verify every reference before editing.

**Option B: add a new enum/format end-to-end.**
New format name, size entry, aspect value, validator range, UI label, SPS
mapping. More correct, much larger surface, needs UI work.

Decision rule: if Option A needs fewer than ~10 sites and no new enum, take it.
Otherwise scope Option B and expect weeks, not days.

**Do not** change 4K or existing 16:9 modes. Keep the patch reversible and
limited to one slot.

---

## 7. Phase 3 — Build and static verify (3–5 days)

1. Write `tools/make_open_gate_patch.py` that applies the offsets to copies of
   `av-cam.bin`, `libObj.so`, `libmpr*.so`, and recomputes every internal
   checksum (WBI checksums, ext2 inode checksums if any, FDAT CRC).
2. Diff every changed byte; assert the original bytes match the recorded
   baseline before patching, so a wrong firmware version fails loudly.
3. Static checks: all validator call sites, SPS fields, table lengths,
   alignment, and no overlap with other formats.
4. Emulation is not available for `av-cam` (bare-metal image). Limit claims to
   static consistency; do not call it "working" before hardware.
5. Keep the patch script and offsets in the repo; never commit patched binaries.

**Deliverable:** reproducible patch set + a dry-run report showing every change.

---

## 8. Phase 4 — Solve installation (parallel from day 1; the long pole)

Investigate in this order, read-only first:

1. **Signed-update bypass.** Document Gen4 verification precisely. Look for
   version/downgrade confusion or guard-check gaps; assume the crypto is sound.
   Do not brute-force keys.
2. **Service mode.** Check whether PMCA/service commands expose partition
   write or a maintenance shell on v1.10. Treat any write as high risk.
3. **Hardware.** Dump the flash, identify partitions and verification. If the
   bootloader verifies `av-cam`, a hardware write alone will not boot. If a
   writable, unverified partition can run a startup script, a runtime patch may
   be possible without touching signed partitions.
4. **Runtime exploit.** The nginx/Node/socket.io userland is a large surface,
   but an exploit is a separate research project with poor reliability. Only
   consider it with a tested recovery path and a clear rollback.

**Deliverable:** `docs/install-path.md` updated with a tested or rejected path.
**Abort:** no path with recovery → stop; do not attempt a one-way write.

---

## 9. Phase 5 — Hardware validation (1 week, only after G0–G3)

Bench unit, charged battery, SD card, room-temperature start.

| Test | Pass condition |
|---|---|
| Boot / power cycle ×20 | no boot loop, no error log |
| Menu shows the new mode | label and settings correct |
| 1080p 16:9 baseline | unchanged files, same bitrate/level |
| New 3:2 mode 24p/30p | records, stops cleanly, file plays on camera |
| `ffprobe` | 1920×1280, SAR 1:1, DAR 3:2, level 5.0 |
| 30-minute record | no thermal shutdown, no dropped frames, no corruption |
| HDMI out | correct framing, no crop/stretch |
| Stills, S&Q, playback | unchanged |
| Restore procedure | camera returns to stock 1.10 and verifies |

Abort on the first corrupt file, thermal warning, or boot loop. Keep the first
unit on a bench, not in the field.

---

## 10. Effort and probability

| Phase | Effort | Probability of success |
|---|---|---|
| G0 install path | 1–2 weeks | **Low** — the main blocker |
| G1 sensor readout | 2–4 days | Medium |
| Phase 1 mapping | 1–2 weeks | High |
| Phase 2–3 patch | 1 week | Medium |
| Phase 5 validation | 1 week | Medium if G0 passes |

Realistic total: 4–8 part-time weeks, most of it on G0. The honest expected
outcome is that G0 fails and the project remains documentation. That is still
useful: it prevents others from bricking cameras chasing the same mode.

---

## 11. Risks

- **Bricking.** Highest risk. No write without a tested restore and a second unit.
- **Signature checks.** A patched FDAT is rejected; a hardware write may fail
  verification at boot.
- **Sensor.** 3:2 video readout may not exist at 24/30 fps.
- **SPS compatibility.** Level 5.0 and non-standard height may break camera
  playback or some editors even when the file is valid.
- **Thermal/memory.** 1920×1280 is modest, but the pipeline may allocate for
  16:9 only.
- **Legal/warranty.** Modifying your own camera may void warranty and may be
  restricted in your jurisdiction. Do not distribute firmware or keys.

---

## 12. First three actions

1. Write `docs/install-path.md`: read the updater verifier and boot scripts,
   answer G0 with evidence.
2. Open `out/avcam.elf` in REA/rizin and finish the validator + format-table
   map; record exact offsets in `docs/patch-map.md`.
3. Search the imager mode table for a 3:2 video-rate readout; answer G1 once the
   fitted part is known.

Do not start patching before 1 and 3 have answers.
