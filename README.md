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
| | A one-byte change at `0x87fe0a` changes that function's returned height from 1080 to 1280 — disassembly-verified offline (`tools/verify_patch.py`). It does not by itself change the record table, sensor readout or SPS. |
| | `liro.ko` checks only `ORIL` at `+4` and version `4` at `+8` — no checksum — so a patched `av-cam.bin` copy loads like the stock one. `im.elf` builds `fn=/system/av-cam.bin …` and calls `init_module` through `syscall()`, so a preload shim can point it at a verified copy on `/log` without writing `/system` (`tools/og.c`). |
| | `init` mounts `/dev/nflasha11` on `/log` before it execs `bootin.elf` (mount call at `0x980c`), read-write. |
| | `tools/verify_record.py` proves the record-822 edit (six bytes) and emits the copy, without touching the source image. |
| | `bootin.elf` reads `/setting/mode/preload` and passes it to `im.elf` as `LD_PRELOAD`; `/usr/bin/change_mode.sh` is Sony's own tool for writing those files. |
| | `init` **unconditionally attempts** to exec `/bin/ash` on a console device at every boot; a usable serial shell is not verified (`docs/uart-shell.md`). |
| **Blocking** | Physical UART test points, logic level and baud rate on the A6600 mainboard are unknown. |
| | `av-cam.bin` contains **IMX284E** imager-driver symbols, but the same image also carries IMX210/IMX094 PSF headers, so it appears shared across models. The fitted part and a 3:2 readout mode at 24/30 fps are unverified. |
| | H.264 SPS/level metadata for a 1280-high stream is unproven. A stock 1080p24 clip is enough to establish the baseline: `ffprobe -show_streams clip.mp4` reports `profile`, `level` and `coded_width/height`. 1920×1280 is 9600 macroblocks, above Level 4.1's MaxFS (8192), so a compliant stream must signal Level 5.0. |
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
- No dimension restriction was found in the visible encoder interface: it takes
  explicit width/height/canvas sizes and is 4K-capable. The closed encoder's SPS
  and level behaviour remains unknown; the blockers are the mode tables, LiroSeq
  validators, UI, sensor readout mode and SPS metadata.
- The a6600 has an **8-bit 4:2:0 AVC** encoder and no HEVC encoder assets.
- No dynamic reference to `GetPictureSize` exists outside `libmpr.so`, so symbol
  interposition cannot reach it; the shim patches the instruction in memory
  instead (`docs/preload-path.md`).
- `im.elf` loads `liro.ko` and passes `fn=/system/av-cam.bin …` via
  `init_module`. `liro.ko` reads the image in kernel space and checks only
  `ORIL` + version 4, no checksum. The kernel read cannot be intercepted, but
  `im.elf` calls `syscall` through its PLT, so a preload shim can rewrite the
  `fn=` path at boot (`docs/patch-map.md`).
- No cryptographic verifier was found in any extractable update code. The
  update runs from the normal OS (`im.elf → libIMDB → libupdaterufp → crypter`)
  and checks CRC32 only; the FDAT's 256-byte trailer is never read by that path.
  Modified updates are **plausibly installable but unproven**
  (`docs/install-path.md`).

## Route (not yet a validated procedure)

The runtime path is promising but incomplete. In order:

1. Prove an interactive serial shell and a write/delete/reboot rollback of a
   harmless file under `/setting/mode/` (`docs/uart-shell.md`).
2. Resolve how record 822's geometry is changed to match the encoder size.
   Best candidate: redirect `liro.ko` to a patched copy through a `syscall`
   interposer, so `/system` is not written. Persistent `/system` patching is the
   fallback (`docs/patch-map.md`).
3. Resolve sensor readout and H.264 SPS/level behaviour.
4. Only then install the complete change, after a verified backup.
5. Record a short 1080p24 clip and inspect it with `ffprobe`; treat any result as
   evidence, not success.

`og.so` on its own changes one size query and does **not** make a valid
open-gate recording. Do not test it alone on the camera.

The update/FDAT route remains the fallback if the UART turns out to be
unavailable or output-only.

## Repo layout

| Path | Contents |
|---|---|
| `docs/open-gate-analysis.md` | Open-gate / 3:2 feasibility: components, dimension tables, validators, verdict |
| `docs/install-path.md` | G0: what the update and boot chain verify, where the FDAT verifier must live, install options |
| `docs/preload-path.md` | `/setting/mode/{dmode,preload}` → `LD_PRELOAD` in `im.elf`; the in-memory patch and its limits |
| `docs/uart-shell.md` | The unconditional shell launch attempt in `init`, and the read-only test protocol |
| `docs/patch-map.md` | Movie record table, candidate 1080 slot for 1920×1280, known bytes, unresolved aspect/level work |
| `docs/implementation-plan.md` | Phased plan: gates G0–G3, phases, test matrix, effort/risk |
| `docs/a6600-vs-a6700.md` | a6600 vs a6700 platform comparison and feature-limit analysis |
| `tools/og.c` | The `LD_PRELOAD` shim: guarded in-memory patch of the encoder size |
| `tools/verify_patch.py` | Offline proof of the byte patch against a real `libmpr.so` |
| `tools/verify_record.py` | Offline proof of the record-822 geometry edit in `av-cam.bin` |
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
python3 tools/verify_patch.py  out/usr/lib/libmpr.so
python3 tools/verify_record.py out/system/av-cam.bin
# before: 0x438 (1080) / record 822 1920x1080
# after:  0x500 (1280) / record 822 1920x1280
# ok

# produce the copy the shim loads, without touching the source image
python3 tools/verify_record.py out/system/av-cam.bin --out patched-av.bin
```

The script is pinned to the **v1.10** updater layout (`BASE=0xAE9D4`,
`SIZE=316672424`); other versions need different offsets and are rejected by the
model/version check.

## Where help is needed

Five questions, in order of usefulness. Each can be answered with evidence and
without touching anyone's camera.

1. **UART on the ILCE-6600 mainboard.** Test-point location, logic level and
   baud rate. A board photo with labelled pads, or the service manual, unblocks
   everything else — the firmware already tries to start a root shell on that
   port (interactivity unproven).
2. **A6600 sensor identity and readout modes.** `av-cam.bin` carries IMX284E
   driver symbols, but it is a shared multi-model image. Confirm which part is
   fitted, then whether it supports a 3:2 crop or binning mode at 24/30 fps
   (e.g. 2120×1416). Datasheet, register table, board marking or timing evidence.
3. **Non-16:9 AVC in any Sony body.** If some Sony camera records a taller than
   16:9 AVC stream, its SPS and level handling is the reference we need.
4. **The `0800_appli` copy step.** Which updater component installs
   `0800_appli/setting/*` onto `nflasha2`, and does it create new
   subdirectories? `uc_mkfs.elf` only runs `mkdosfs`; the copy is elsewhere.
5. **`av-cam.bin` runtime delivery.** `im.elf` passes
   `fn=/system/av-cam.bin load=1 debug=1 adr=…` to `liro.ko`, which reads the
   file in kernel space and checks only `ORIL` + version 4. We now redirect that
   `fn=` path through a `syscall` interposer to a patched copy on `/log`
   (`tools/og.c`). What is missing is a way to place 16.8 MB on `/log` without a
   root shell, and evidence that `liro` accepts the redirected path at boot.

A bricked or donor A6600 board, or a service manual, is worth more than any
amount of speculation. If you can answer one of these with reproducible
evidence, open an issue.

## Safety

- Do **not** flash a modified FDAT. The update path has no visible signature
  check, but the 256-byte trailer is unexplained and there is no verified
  recovery path. Treat acceptance as unproven.
- **Do not run `og.so` alone.** The camera's capture record still describes
  1920×1080 while the encoder would be told 1920×1280; that mismatch is untested
  and may corrupt the recording or the application.
- A broken preload library can boot-loop the camera. It is only safely testable
  once an interactive serial shell and a proven file rollback exist.
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
