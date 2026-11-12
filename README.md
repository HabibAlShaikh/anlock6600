# Sony a6600 (ILCE-6600) — open-gate 1080p

Read-only reverse engineering of the Sony **ILCE-6600**, firmware **1.10**
(`38114_02.2020071501`), with one goal: record **1920×1280 (3:2) at 24p** using
the existing 1080p record slot, without bricking the camera.

This repository contains **text, offsets, scripts and hashes only.** No Sony
firmware, no keys, no patched images.

## Status

| | |
|---|---|
| **Proven** | The 1.10 extraction is reproducible and hash-checked (`scripts/extract_a6600.py`, `verify: ok`). |
| | Encoder dimensions come from `MprLibCore::GetPictureSize()` in `libmpr.so` (`0x87fdd4`); code 2 is 1920×1080. |
| | A one-byte change at `0x87fe0a` turns that case into 1920×1280 — disassembly-verified offline (`tools/verify_patch.py`). |
| | `bootin.elf` reads `/setting/mode/preload` and passes it to `im.elf` as `LD_PRELOAD`; `/usr/bin/change_mode.sh` is Sony's own tool for writing those files. |
| | `init` starts an unauthenticated **root shell on the serial console at every boot** (`docs/uart-shell.md`). |
| **Blocking** | Physical UART test points, logic level and baud rate on the A6600 mainboard are unknown. |
| | IMX284 3:2 readout at 24/30 fps is unproven. |
| | H.264 SPS/level metadata for a 1280-high stream is unproven. |
| | The update step that copies `0800_appli/setting/*` onto `nflasha2` is not identified. |
| | FDAT 256-byte trailer acceptance is unresolved (matters only for the flash route). |
| **Unknown** | Whether the validators, LiroSeq and UI accept a 3:2 canvas end to end. |
| | `CapIdTblMgr` / `PARAMID_CAP_INFO_*` format and the a6600's enabled list. |

Nothing has been written to the camera. No flashing has been attempted.

## What was found

- The movie path is **enum-quantised**: size classes are
  `PICT_SIZE_VGA / 720 / 1080 / 2160`, and all 39 movie format names use a
  height of 270, 360, 480, 720, 1080 or 2160.
- Movie aspect is limited to **16:9**. The `4:3` and `15:9` IDs in `libObj.so`
  are AVCHD/pixel-aspect metadata, not selectable recording modes.
- The only 1440×1080 movie path is **anamorphic 16:9** (displays as 1920×1080).
- 1920×1280 and 1920×1440 exist **only as still-photo sizes**. They never enter
  `av-cam.bin` or any movie format name.
- The AVC encoder is **not the limit**: it accepts explicit width/height/canvas
  sizes, is 4K-capable, and 1920×1280 is well inside its limits. The blockers are
  the mode tables, LiroSeq validators, UI, sensor readout mode and SPS metadata.
- The a6600 has an **8-bit 4:2:0 AVC** encoder and no HEVC encoder assets.
- `GetPictureSize` is called only from inside `libmpr.so`, so symbol
  interposition cannot reach it; the shim patches the instruction in memory
  instead (`docs/preload-path.md`).
- No cryptographic verifier was found in any extractable update code. The
  update runs from the normal OS (`im.elf → libIMDB → libupdaterufp → crypter`)
  and checks CRC32 only; the FDAT's 256-byte trailer is never read by that path.
  Modified updates are **plausibly installable but unproven**
  (`docs/install-path.md`).

## Route

The working plan avoids flashing entirely:

1. Reach the serial shell (`docs/uart-shell.md`) → dump partitions to SD.
2. Copy `tools/og.so` to `/setting/mode/`, run
   `change_mode.sh p /setting/mode/og.so`, reboot (`docs/preload-path.md`).
3. Record 1080p24, check with `ffprobe`. Expect 1920×1280 with a wrong 16:9 DAR
   on the first pass; the aspect/SPS fix is a separate step.
4. Only then decide whether a permanent per-slot implementation is worth it.

The update/FDAT route is the fallback if the UART turns out to be output-only.

## Repo layout

| Path | Contents |
|---|---|
| `docs/open-gate-analysis.md` | Open-gate / 3:2 feasibility: components, dimension tables, validators, verdict |
| `docs/install-path.md` | G0: what the update and boot chain verify, where the FDAT verifier must live, install options |
| `docs/preload-path.md` | `/setting/mode/{dmode,preload}` → `LD_PRELOAD` in `im.elf`; the in-memory patch and its limits |
| `docs/uart-shell.md` | The root shell `init` starts on the serial console, and the read-only test protocol |
| `docs/patch-map.md` | Movie record table, candidate 1080 slot for 1920×1280, known bytes, unresolved aspect/level work |
| `docs/implementation-plan.md` | Phased plan: gates G0–G3, phases, test matrix, effort/risk |
| `docs/a6600-vs-a6700.md` | a6600 vs a6700 platform comparison and feature-limit analysis |
| `tools/og.c` | The `LD_PRELOAD` shim: guarded in-memory patch of the encoder size |
| `tools/verify_patch.py` | Offline proof of the byte patch against a real `libmpr.so` |
| `research/manifests/a6600-files.txt` | File listing of the decrypted firmware package |
| `research/data/` | Dimension scan output, updater strings, annotated hex dump, FDAT round-trip log |
| `research/scripts/` | Small analysis helpers (container layout, dimension scan, xrefs, av-cam ELF reconstruction) |
| `scripts/extract_a6600.py` | Official updater → decrypted FDAT → firmware tree, rootfs, `/usr`, system files |
| `manifests/sha256.txt` | SHA-256 of key generated artifacts (input hashes are comments) |

## Reproduce

Requirements: Python 3, `pycryptodomex`, `tar`, `debugfs` (e2fsprogs), `7z`
(p7zip), `llvm-objdump`, `clang` with `lld` (for `tools/build_og.sh`), and
[ma1co/fwtool.py](https://github.com/ma1co/fwtool.py).

```sh
git clone https://github.com/ma1co/fwtool.py
export PYTHONPATH="$PWD/fwtool.py"
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install pycryptodomex

# Download the official v1.10 updater for your region from Sony support, then:
python3 scripts/extract_a6600.py Update_ILCE6600V110.exe out
```

The script checks the input model/version, fails fast on missing tools, and
verifies the generated files against `manifests/sha256.txt` automatically.

```
out/a6600_fdat.bin        decrypted FDAT
out/a6600_firmware.tar    update payload (config, partitions, lenses)
out/a6600_updater.img     updater filesystem
out/firmware/             unpacked payload
out/rootfs/               root filesystem (ext2, nflasha7)
out/usr/                  /usr partition (ext2, nflasha15)
out/system/               FAT image contents: av-cam.bin, vmlinux.bin, initrd.img, ...
```

Check the patch offline, no camera needed:

```sh
tools/build_og.sh
python3 tools/verify_patch.py out/usr/lib/libmpr.so
# before: 0x438 (1080)
# after:  0x500 (1280)
# ok
```

The script is pinned to the **v1.10** updater layout (`BASE=0xAE9D4`,
`SIZE=316672424`); other versions need different offsets and are rejected by the
model/version check.

## Where help is needed

Four questions, in order of usefulness. Each can be answered with evidence and
without touching anyone's camera.

1. **UART on the ILCE-6600 mainboard.** Test-point location, logic level and
   baud rate. A board photo with labelled pads, or the service manual, unblocks
   everything else — the firmware already starts a root shell on that port.
2. **IMX284 readout modes.** Does the sensor support a 3:2 crop or binning mode
   at 24/30 fps (e.g. 2120×1416)? Datasheet, register table or timing evidence.
3. **Non-16:9 AVC in any Sony body.** If some Sony camera records a taller than
   16:9 AVC stream, its SPS and level handling is the reference we need.
4. **The `0800_appli` copy step.** Which updater component installs
   `0800_appli/setting/*` onto `nflasha2`, and does it create new
   subdirectories? `uc_mkfs.elf` only runs `mkdosfs`; the copy is elsewhere.

A bricked or donor A6600 board, or a service manual, is worth more than any
amount of speculation. If you can answer one of these with reproducible
evidence, open an issue.

## Safety

- Do **not** flash a modified FDAT. The update path has no visible signature
  check, but the 256-byte trailer is unexplained and there is no verified
  recovery path. Treat acceptance as unproven.
- A broken preload library can boot-loop the camera. It is only safely testable
  once the serial shell is reachable.
- Do not write unknown PTP properties or invoke backup/restore, registration or
  power-control commands on a camera you cannot afford to lose.
- Charge the battery before any camera-side testing.
- a6700 material appears **only in the comparison document**. Cross-flashing is
  not possible (different SoC, architecture, layout, IDs and signing) and will
  brick the camera.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Short version: reproducible scripts,
file offsets, and evidence. No firmware uploads, no keys, no "just flash this".

## License

Original text and scripts: MIT (see [`LICENSE`](LICENSE)). Sony firmware,
trademarks and third-party tools remain the property of their owners and are not
distributed here.
