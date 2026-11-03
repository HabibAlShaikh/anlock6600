# Research scripts

Run these from the repo root after `scripts/extract_a6600.py ... out`.
Paths are optional arguments; defaults point into `out/`.

| Script | Usage | Purpose |
|---|---|---|
| `scan_dims.py` | `scan_dims.py DIR...` | Scan files for width/height-like u32 pairs and dump candidates |
| `inspect_updater.py` | `inspect_updater.py Update.exe` | Print DAT chunk layout, verify DAT CRC32, split the FDAT ciphertext/IV/trailer |
| `fdat_roundtrip.py` | `fdat_roundtrip.py Update.exe OUTDIR` | Decrypt/re-encrypt the FDAT and prove a byte-identical DAT rebuild (needs fwtool + pycryptodomex) |
| `recon_avcam.py` | `recon_avcam.py [av-cam.bin]` | Summarise the image (size, header, high-word histogram) |
| `mkelf.py` | `mkelf.py [av-cam.bin] [avcam.elf]` | Wrap the raw ARM image in a minimal ELF for a disassembler |
| `xref_pic2.py` | `xref_pic2.py [av-cam.bin] [picrefs2.json]` | Find references to picture-size constants |
| `find_strtab.py` | `find_strtab.py [av-cam.bin]` | Locate LiroSeq string tables and their entries |
| `find_selfrel.py` | `find_selfrel.py [av-cam.bin]` | Find self-relative pointers to known strings |
| `rng.py` | `rng.py LO HI [avcam.dis]` | Print disassembly lines in an address range |

The ELF has no symbol table; it is only a load container for the raw ARM image.
`rng.py` needs `out/avcam.dis`, which is not shipped (225 MB). Generate it with:

```sh
llvm-objdump --triple=thumbv7-linux-gnueabihf -d out/avcam.elf > out/avcam.dis
```
