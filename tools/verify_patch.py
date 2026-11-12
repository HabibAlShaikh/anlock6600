#!/usr/bin/env python3
"""Dry-run check for tools/og.c against a real libmpr.so.

Validates the two things the shim relies on: the baseline instruction bytes and
the effect of the single-byte edit. Writes only to a temp directory.

    python3 tools/verify_patch.py out/usr/lib/libmpr.so
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FUNC = 0x87FDD4          # MprLibCore::GetPictureSize
INSN = FUNC + 0x34       # mov.w r3, #0x438
PATCH = INSN + 2         # the 0x87 immediate byte
EXPECT = bytes.fromhex("4ff48763")


def height_at(path, addr):
    """Decode the mov.w r3 immediate at addr. Returns None if not a mov.w."""
    out = subprocess.run(
        ["llvm-objdump", "-d", "--triple=thumbv7", "--no-show-raw-insn",
         f"--start-address={addr:#x}", f"--stop-address={addr + 4:#x}", str(path)],
        capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if "mov.w" in line and "#" in line:
            return int(line.split("#")[1].strip(), 16)
    return None


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "out/usr/lib/libmpr.so")
    data = bytearray(src.read_bytes())

    got = bytes(data[INSN:INSN + 4])
    if got != EXPECT:
        sys.exit(f"baseline mismatch at {INSN:#x}: {got.hex(' ')}")

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "libmpr.so"
        shutil.copyfile(src, copy)
        data[PATCH] = 0xA0
        copy.write_bytes(data)

        before = height_at(src, INSN)
        after = height_at(copy, INSN)

    print(f"before: 0x{before:x} ({before})")
    print(f"after:  0x{after:x} ({after})")
    if before != 1080 or after != 1280:
        sys.exit("unexpected result")
    print("ok")


if __name__ == "__main__":
    main()
