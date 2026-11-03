# Contributing

This is a read-only research repo. The goal is evidence other people can check,
not a firmware download or a flashing guide.

## What helps

- A reproducible script plus its output (small text/JSON/TSV, not binaries).
- Exact file offsets and the bytes around them.
- A clear split between **proven** (observed in the image / on hardware) and
  **inferred** (your interpretation).
- Negative results: "searched X, found nothing" is useful and will be recorded.

## What not to send

- Firmware images, decrypted FDATs, rootfs dumps, `.exe`/`.DAT`/`.bin` files.
- Decryption keys or key-derivation material.
- Instructions that require flashing an unverified image.
- Camera serial numbers or other personal identifiers in logs/screenshots.

## Workflow

1. Open an issue describing the question and the file/offset you will inspect.
2. Keep changes small: one question per PR.
3. Run `python3 -m py_compile` on changed scripts and include the command you used.
4. Update the relevant doc in `docs/` if your result changes a conclusion.

## Style

- Markdown, short sections, tables where they help.
- Use file offsets, not virtual addresses, unless you say which is which.
- Cite the source file and firmware version (`a6600 v1.10`).
