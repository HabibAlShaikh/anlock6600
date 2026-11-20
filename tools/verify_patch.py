#!/usr/bin/env python3
"""Dry-run check for tools/og.c against the pinned a6600 v1.10 libmpr.so.

Proves the baseline bytes, the ELF address mapping, the symbol identity, and
that the edit changes exactly one byte and decodes as 1280. It does not prove
that the shim loads on the camera or that the recording pipeline accepts the
size. Writes only to a temp directory.

    python3 tools/verify_patch.py out/usr/lib/libmpr.so
"""

import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

# a6600 v1.10, extracted from the official updater.
EXPECTED_SHA256 = "0a57805b6c27ba5f107e7cb1bf4ff2be605967e22e22f08274d8ae3b78a6e67a"
SYMBOL = "_ZN10MprLibCore14GetPictureSizeEN3MPR11VResolutionEPtS2_"
SYMBOL_VA = 0x0087FDD5      # Thumb function value (bit 0 set)
SYMBOL_SIZE = 180
INSN_VA = 0x0087FE08        # mov.w r3, #0x438
EXPECT = bytes.fromhex("4ff48763")
PT_LOAD = 1


def vaddr_to_offset(data, vaddr, size=4):
    """Map a virtual address to a file offset using ELF32 program headers."""
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
        sys.exit("not a little-endian ELF32 file")
    phoff = struct.unpack_from("<I", data, 0x1C)[0]
    phentsize = struct.unpack_from("<H", data, 0x2A)[0]
    phnum = struct.unpack_from("<H", data, 0x2C)[0]
    for i in range(phnum):
        base = phoff + i * phentsize
        p_type, p_offset, p_vaddr, _, p_filesz = struct.unpack_from("<IIIII", data, base)
        if p_type != PT_LOAD:
            continue
        if p_vaddr <= vaddr and vaddr + size <= p_vaddr + p_filesz:
            return p_offset + (vaddr - p_vaddr)
    sys.exit(f"{vaddr:#x} is not inside a file-backed PT_LOAD segment")


def check_symbol(path):
    out = subprocess.run(["readelf", "--dyn-syms", "-W", str(path)],
                         capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        fields = line.split()
        if fields and fields[-1] == SYMBOL:
            value = int(fields[1], 16)
            size = int(fields[2])
            if value != SYMBOL_VA or size != SYMBOL_SIZE:
                sys.exit(f"symbol mismatch: value={value:#x} size={size}")
            return
    sys.exit(f"symbol not found: {SYMBOL}")


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

    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        sys.exit(f"not the pinned a6600 v1.10 libmpr.so\n"
                 f"  expected {EXPECTED_SHA256}\n  got      {digest}")

    check_symbol(src)
    insn_off = vaddr_to_offset(data, INSN_VA)
    patch_off = vaddr_to_offset(data, INSN_VA + 2, size=1)

    got = bytes(data[insn_off:insn_off + 4])
    if got != EXPECT:
        sys.exit(f"baseline mismatch at {INSN_VA:#x} (file {insn_off:#x}): {got.hex(' ')}")

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "libmpr.so"
        data[patch_off] = 0xA0
        changes = sum(a != b for a, b in zip(src.read_bytes(), data))
        copy.write_bytes(data)

        before = height_at(src, INSN_VA)
        after = height_at(copy, INSN_VA)

    if changes != 1:
        sys.exit(f"expected exactly one changed byte, got {changes}")
    print(f"before: 0x{before:x} ({before})")
    print(f"after:  0x{after:x} ({after})")
    if before != 1080 or after != 1280:
        sys.exit("unexpected result")
    print("ok: one byte changed, 1080 -> 1280")


if __name__ == "__main__":
    main()
