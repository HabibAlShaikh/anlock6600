# Sony a6600 (ILCE-6600) firmware research

Read-only reverse engineering of the Sony **ILCE-6600** firmware, version **1.10**
(internal build string `38114_02.2020071501`), focused on video capabilities —
specifically whether an **open-gate (3:2) 1080p** recording mode can be enabled.

**Status: negative so far.** No stock setting or PTP property was found that
enables a taller-than-16:9 movie frame; service-mode capability data is still
unknown. Doing it would require patching the firmware. No signature verifier was
found in the extractable update path, so an install is plausibly possible, but it
is unproven and has not been tested on hardware.

This repository contains **text, offsets, scripts and hashes only**. It does not
contain Sony firmware or decrypted firmware images; see [Reproduce](#reproduce).

## What was found

- The movie path is **enum-quantised**: size classes are
  `PICT_SIZE_VGA / 720 / 1080 / 2160`, and every one of the 39 movie format
  names uses a height of 270, 360, 480, 720, 1080 or 2160.
- Movie aspect is limited to **16:9**. The `4:3` and `15:9` IDs in `libObj.so`
  are AVCHD/pixel-aspect metadata, not selectable recording modes.
- The only 1440×1080 movie path is **anamorphic 16:9** (displays as 1920×1080).
- 1920×1280 and 1920×1440 exist **only as still-photo sizes** in generic aspect
  tables. They never enter `av-cam.bin` or any movie format name.
- The AVC encoder is **not the limit**: it accepts explicit width/height/canvas
  sizes, is 4K-capable, and 1920×1280 is well inside its limits. The blockers are
  the mode tables, LiroSeq validators, UI, sensor readout mode and SPS metadata.
- The a6600 has an **8-bit 4:2:0 AVC** encoder and no HEVC encoder assets.
- No cryptographic verifier was found in any extractable update code: the update
  runs from the normal OS (`im.elf → libIMDB → libupdaterufp → crypter`) and
  checks CRC32 only. The FDAT's 256-byte trailer is never read by that path, so
  modified updates are **plausibly installable but unproven**; the trailer and
  the loader/ROM remain unexplained. See
  [`docs/install-path.md`](docs/install-path.md).

Full detail: [`docs/open-gate-analysis.md`](docs/open-gate-analysis.md),
[`docs/install-path.md`](docs/install-path.md) and
[`docs/a6600-vs-a6700.md`](docs/a6600-vs-a6700.md).

## Repo layout

| Path | Contents |
|---|---|
| `docs/open-gate-analysis.md` | Open-gate / 3:2 feasibility: components, dimension tables, validators, verdict |
| `docs/install-path.md` | G0: what the update and boot chain verify, where the FDAT verifier must live, install options |
| `docs/patch-map.md` | Movie record table, candidate 1080 slot for 1920×1280, known bytes, and unresolved aspect/level work |
| `docs/implementation-plan.md` | Phased plan: gates G0–G3, phases, test matrix, effort/risk |
| `docs/a6600-vs-a6700.md` | a6600 vs a6700 platform comparison and feature-limit analysis |
| `research/manifests/a6600-files.txt` | File listing of the decrypted firmware package |
| `research/data/` | Dimension scan output, updater strings, annotated hex dump, FDAT round-trip log |
| `research/scripts/` | Small analysis helpers (container layout, dimension scan, xrefs, av-cam ELF reconstruction) |
| `scripts/extract_a6600.py` | Official updater → decrypted FDAT → firmware tree, rootfs, `/usr`, system files |
| `manifests/sha256.txt` | SHA-256 of key generated artifacts (input hashes are comments) |

## Reproduce

Requirements: Python 3, `pycryptodomex`, `tar`, `debugfs` (e2fsprogs), `7z`
(p7zip), and [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py).

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

Output:

```
out/a6600_fdat.bin        decrypted FDAT
out/a6600_firmware.tar    update payload (config, partitions, lenses)
out/a6600_updater.img     updater filesystem
out/firmware/             unpacked payload
out/rootfs/               root filesystem (ext2, nflasha7)
out/usr/                  /usr partition (ext2, nflasha15)
out/system/               FAT image contents: av-cam.bin, vmlinux.bin, initrd.img, ...
```

Manual re-check: `cd out && sha256sum -c ../manifests/sha256.txt`.
The script is pinned to the **v1.10** updater layout (`BASE=0xAE9D4`,
`SIZE=316672424`); other versions need different offsets and are rejected by
the model/version check.

## Open questions — where help is useful

1. **Capability-ID tables.** Movie modes are gated at runtime by `CapIdTblMgr` /
   `PARAMID_CAP_INFO_*` data in encrypted model partitions. The format and the
   a6600's enabled list are unknown. A read-only service-mode backup might
   expose enough to document it.
2. **Validator mapping.** Fully disassemble the `av-cam.bin` LiroSeq checks
   (`mov_aspect_req`, `mov_size_req`, `mov_sizeh_req`, `movrec_mode_req`) and
   confirm how the size enum maps to the image-size tables.
3. **Sensor readout.** Does the IMX284 support a 3:2 binning mode at video rates
   (e.g. 2120×1416)? Datasheet, teardown or timing evidence wanted.
4. **Shared binary comparison.** The a6600 `av-cam.bin` is a multi-model image.
   Comparing it with other Sony bodies that share the binary could reveal whether
   a 3:2 movie path exists anywhere and is merely gated.
5. **`0xd406`.** This PTP string property is the only writable one and is always
   empty. Its purpose is unknown. Observe it read-only; do not write it blindly.

If you can answer one of these with reproducible evidence, open an issue or PR.

## Safety

- Do **not** flash a modified FDAT. The update path has no visible signature
  check, but the 256-byte trailer is unexplained and there is no verified
  recovery path. Treat acceptance as unproven.
- Do not write unknown PTP properties or invoke backup/restore, registration or
  power-control commands on a camera you cannot afford to lose.
- Charge the battery before any camera-side testing. The unit used here was at
  17–19% during inspection.
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
