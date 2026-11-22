#!/usr/bin/env python3
"""Dry-run check for the record-822 geometry edit in av-cam.bin.

Validates the pinned a6600 v1.10 image, the ORIL header that liro.ko checks,
the current record bytes, and that the proposed edit changes only the intended
six bytes. With no --out it writes only to a temp directory and deletes it.

    python3 tools/verify_record.py out/system/av-cam.bin
    python3 tools/verify_record.py out/system/av-cam.bin --out /log/og-av.bin
"""

import hashlib
import struct
import sys
import tempfile
from pathlib import Path

EXPECTED_SHA256 = "c17bdd14bb3f51ab14b6ffcd385b81786c4201ab5a0d2bea8a2c7be5c6aed8b5"
HEADER = bytes.fromhex("0a0000ea4f52494c04000000")  # b + "ORIL" + version 4
RECORD = 0x879C54
SIZE_1080 = struct.pack("<HH", 1920, 1080)
SIZE_1280 = struct.pack("<HH", 1920, 1280)

# file offset, current, proposed
EDITS = (
    (RECORD + 0x04, SIZE_1080, SIZE_1280),   # packed w/h
    (RECORD + 0x34, struct.pack("<I", 1088), struct.pack("<I", 1288)),  # height+8
    (RECORD + 0x48, SIZE_1080, SIZE_1280),   # packed canvas/valid size
)


def main():
    args = sys.argv[1:]
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        out_path = Path(args[i + 1])
        del args[i:i + 2]
    src = Path(args[0] if args else "out/system/av-cam.bin")
    data = bytearray(src.read_bytes())

    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        sys.exit(f"not the pinned a6600 v1.10 av-cam.bin\n"
                 f"  expected {EXPECTED_SHA256}\n  got      {digest}")
    if bytes(data[:12]) != HEADER:
        sys.exit(f"unexpected header: {bytes(data[:12]).hex(' ')}")
    if data[RECORD] != 6:
        sys.exit(f"record 822 class is {data[RECORD]}, expected 6")
    if data[RECORD + 0x0C] != 3:
        sys.exit(f"record 822 rate key is {data[RECORD + 0x0C]}, expected 3")

    original = bytes(data)
    for off, current, proposed in EDITS:
        got = bytes(data[off:off + len(current)])
        if got != current:
            sys.exit(f"baseline mismatch at {off:#x}: {got.hex(' ')}")
        data[off:off + len(proposed)] = proposed

    changed = sum(a != b for a, b in zip(original, data))
    if changed != 6:
        sys.exit(f"expected exactly 6 changed bytes, got {changed}")
    if len(data) != len(original):
        sys.exit("file size changed")

    if out_path:
        out_path.write_bytes(data)
        out = out_path.read_bytes()
        print(f"wrote {out_path} ({len(out)} bytes)")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "av-cam.bin"
            copy.write_bytes(data)
            out = copy.read_bytes()

    w, h = struct.unpack_from("<HH", out, RECORD + 0x04)
    canvas_w, canvas_h = struct.unpack_from("<HH", out, RECORD + 0x48)
    height8 = struct.unpack_from("<I", out, RECORD + 0x34)[0]
    print(f"record 822: {w}x{h}, canvas {canvas_w}x{canvas_h}, +0x34 {height8}")
    if (w, h, canvas_w, canvas_h, height8) != (1920, 1280, 1920, 1280, 1288):
        sys.exit("unexpected result")
    print("ok: 6 bytes changed, header and size preserved")


if __name__ == "__main__":
    main()
