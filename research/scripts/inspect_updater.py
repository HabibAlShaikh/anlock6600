#!/usr/bin/env python3
"""Describe the update container inside a Sony updater executable.

Reads the raw DAT (magic \\x89UFU\\r\\n\\x1a\\n) embedded in the .exe, verifies its
CRC32, lists the chunks, and splits the encrypted FDAT into
ciphertext + 16-byte IV + 256-byte trailer. No Sony keys needed.

Usage: python3 inspect_updater.py Update_ILCE6600V110.exe
"""

import binascii
import hashlib
import sys

DAT_MAGIC = b"\x89UFU\r\n\x1a\n"
CHUNK_HEADER = 8


def find_dat(data):
    off = data.find(DAT_MAGIC)
    if off < 0:
        sys.exit("DAT magic not found (not a Sony updater exe?)")
    return off


def read_chunks(data, base):
    if not data.startswith(DAT_MAGIC, base):
        sys.exit("bad DAT magic at 0x%x" % base)
    off = base + len(DAT_MAGIC)
    chunks = []
    while True:
        size = int.from_bytes(data[off:off + 4], "big")
        ctype = data[off + 4:off + 8]
        body = off + CHUNK_HEADER
        if body + size > len(data):
            sys.exit("truncated DAT: chunk %r claims %d bytes" % (ctype, size))
        chunks.append((ctype, body, size))
        off = body + size
        if ctype == b"DEND":
            return chunks, off


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data = open(sys.argv[1], "rb").read()
    base = find_dat(data)
    chunks, end = read_chunks(data, base)
    print("DAT     offset=0x%x size=%d" % (base, end - base))
    for ctype, body, size in chunks:
        print("  %-4s offset=0x%x size=%d" % (ctype.decode("ascii", "replace"), body, size))

    # DEND.crc covers every byte before the DEND chunk header.
    dend_body = chunks[-1][1]
    stored = int.from_bytes(data[dend_body:dend_body + 4], "big")
    calc = binascii.crc32(data[base:dend_body - CHUNK_HEADER]) & 0xFFFFFFFF
    print("DAT crc stored=0x%08x calc=0x%08x %s" % (stored, calc, "OK" if stored == calc else "MISMATCH"))

    fdat = [c for c in chunks if c[0] == b"FDAT"]
    if not fdat:
        sys.exit("no FDAT chunk")
    _, body, size = fdat[0]
    if size < 0x110:
        sys.exit("FDAT too small for the Gen4 trailer")
    cipher_len = size - 0x110
    iv = data[body + cipher_len:body + cipher_len + 16]
    trailer = data[body + cipher_len + 16:body + size]
    print("FDAT    ciphertext=%d (%%%d=%d)" % (cipher_len, 1024, cipher_len % 1024))
    print("        iv=%s" % iv.hex())
    print("        trailer=%d bytes sha256=%s nonzero=%d" %
          (len(trailer), hashlib.sha256(trailer).hexdigest(), sum(1 for b in trailer if b)))


if __name__ == "__main__":
    main()
