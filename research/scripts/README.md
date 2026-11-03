# Research scripts

These are the small helpers used during the analysis. They are not a stable
toolchain; they assume the extraction layout from `scripts/extract_a6600.py`
(or the original `/tmp/opencode` layout).

| Script | Purpose |
|---|---|
| `scan_dims.py` | Scan an image for width/height-like u32 pairs and dump candidates |
| `xref_pic2.py` | Find references to picture-size constants in a binary |
| `find_strtab.py` | Locate string tables and their entries |
| `find_selfrel.py` | Find self-relative pointers in a raw image |
| `recon_avcam.py` | Summarise `av-cam.bin` (size, header, high-word histogram) |
| `mkelf.py` | Wrap `av-cam.bin` in a minimal ELF so a disassembler will load it |

`mkelf.py` writes `open_gate/avcam.elf`; create that directory first or change
the output path. The generated ELF has no symbol table — it is only a load
container for the raw ARM image.
