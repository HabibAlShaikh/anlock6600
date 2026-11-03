#!/usr/bin/env python3
"""Find Thumb PC-relative xrefs in a raw ARM blob.

Handles both idioms:
  ldr rX,[pc,#imm]             -> pool word is an ABSOLUTE address
  ldr rX,[pc,#imm]; add rX,pc  -> pool word is (target - (insn+4))

Reports resolved targets inside a requested address range.

Usage: xref_thumb.py FILE LO HI
  xref_thumb.py out/system/av-cam.bin 0x87990c 0x879e4c
  xref_thumb.py out/usr/lib/libmpr.so 0x376f8 0x37710
"""

import struct
import sys


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    path = sys.argv[1]
    lo, hi = int(sys.argv[2], 0), int(sys.argv[3], 0)
    d = open(path, 'rb').read()

    def word(o):
        return struct.unpack_from('<I', d, o)[0]

    hits = []
    for s in range(0, len(d) - 4, 2):
        h = struct.unpack_from('<H', d, s)[0]
        # 01001xxx xxxxxxxx : ldr rX,[pc,#imm8*4]
        if (h & 0xF800) != 0x4800:
            continue
        rt = (h >> 8) & 7
        imm = (h & 0xFF) * 4
        pool = ((s + 4) & ~3) + imm
        if pool + 4 > len(d):
            continue
        w = word(pool)
        # idiom A: absolute pointer
        if lo <= w < hi:
            hits.append((s, 'abs', w))
        # idiom B: offset added to pc by a following `add rX,pc`
        for k in (2, 4):
            if s + k + 2 > len(d):
                break
            n = struct.unpack_from('<H', d, s + k)[0]
            if (n & 0xFF87) == 0x4478 and ((n >> 8) & 7) == rt:  # add rX, pc
                t = (w + s + k + 4) & 0xFFFFFFFF
                if lo <= t < hi:
                    hits.append((s, 'pc+', t))
                break

    hits.sort()
    print("%d xrefs into [%#x,%#x)" % (len(hits), lo, hi))
    for s, kind, t in hits:
        print("  insn %#08x  %s  -> %#08x" % (s, kind, t))


if __name__ == '__main__':
    main()
