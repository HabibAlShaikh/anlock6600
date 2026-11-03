#!/usr/bin/env python3
"""Byte-identical FDAT/DAT round-trip for a Sony updater.

Proves the Gen4 container can be rebuilt: decrypt the FDAT, re-encrypt the same
plaintext, rebuild the DAT and compare byte-for-byte. This is a proof tool, not
a camera image writer.

Run (needs fwtool.py on PYTHONPATH and pycryptodomex):
  export PYTHONPATH=/path/to/fwtool.py
  python3 research/scripts/fdat_roundtrip.py Update_ILCE6600V110.exe /tmp/roundtrip
"""
import io
import os
import struct
import sys
import zlib

from Cryptodome.Cipher import AES

from fwtool.sony import constants, fdat

EXE = sys.argv[1] if len(sys.argv) > 1 else 'Update_ILCE6600V110.exe'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/tmp/fdat-roundtrip'
DAT_OFF = 0xAE9D4
BLOCK = 1024              # AesCbcCrypter.decryptBlock size
PAYLOAD = BLOCK - 4       # BlockCrypter strips 4-byte header -> 1020
TRAILER = 0x110           # IV(16) + trailer(256)
MAGIC = b'\x89UFU\r\n\x1a\n'
DEND = b'DEND'


def walk_chunks(buf):
    """[(type, data_off, size, header_off)] plus end offset. Big-endian headers."""
    assert buf[:8] == MAGIC, buf[:8]
    out, off = [], 8
    while off + 8 <= len(buf):
        size, typ = struct.unpack('>i4s', buf[off:off + 8])
        out.append((typ, off + 8, size, off))
        off += 8 + size
        if typ == DEND:
            break
    return out, off


def encrypt_fdat(plain, iv):
    """Inverse of AesCbcCrypter.decrypt (CXD90045 / key_aes).

    Decrypt, per 1024-byte block d:
      first : AES-ECB_dec(key_aes, d[:512]) || AES-CBC_dec(key_cxd90045, iv)[d[512:]]
      later : AES-CBC_dec[key_cxd90045] over the whole block (same chain)
    then BlockCrypter.unpackBlock: u16le checksum of d[2:] at d[0:2];
      d[2:4] = size | 0x8000(end flag); payload = d[4:4+size].
    So: packBlock(chunk), then ECB first 512, CBC the rest with the original IV.
    """
    ecb = AES.new(constants.key_aes, AES.MODE_ECB)
    cbc = None
    out = bytearray()
    pos, n = 0, len(plain)
    while pos < n:
        chunk = plain[pos:pos + PAYLOAD]
        pos += len(chunk)
        flag = 0x8000 if pos >= n else 0
        body = struct.pack('<H', len(chunk) | flag) + chunk + b'\xff' * (PAYLOAD - len(chunk))
        block = struct.pack('<H', sum(struct.unpack('<511H', body)) & 0xffff) + body
        assert len(block) == BLOCK
        if cbc is None:
            cbc = AES.new(constants.key_cxd90045, AES.MODE_CBC, iv)
            out += ecb.encrypt(block[:512]) + cbc.encrypt(block[512:])
        else:
            out += cbc.encrypt(block)
    return bytes(out)


def compare(a, b):
    """(first_diff_offset_or_None, differing_byte_count), C-speed per 1 MB chunk
    (ChunkedFile.read() without a size is quadratic, so we also avoid read())."""
    CH = 1 << 20
    first = None
    diff = 0
    n = min(len(a), len(b))
    for i in range(0, n, CH):
        ac, bc = bytes(a[i:i + CH]), bytes(b[i:i + CH])
        if ac != bc:
            x = int.from_bytes(ac, 'big') ^ int.from_bytes(bc, 'big')
            diff += x.bit_count()
            if first is None:
                xb = x.to_bytes(len(ac), 'big')
                first = i + (len(xb) - len(xb.lstrip(b'\0')))
    if len(a) != len(b) and first is None:
        first = n
    return first, diff


def main():
    with open(EXE, 'rb') as f:
        f.seek(DAT_OFF)
        head = f.read(0x1000)
        chunks, _ = walk_chunks(head)
        # walk stops before DEND when FDAT is huge; DEND is 8-byte header + 4 CRC
        last = chunks[-1]
        total = last[3] + 8 + last[2] + (0 if last[0] == DEND else 12)
        f.seek(DAT_OFF)
        dat = f.read(total)

    chunks, dat_end = walk_chunks(dat)
    assert dat_end == total, (dat_end, total)
    print('DAT size %d, chunks %s' % (len(dat), [c[0].decode() for c in chunks]))

    _, foff, fsize, _ = [c for c in chunks if c[0] == b'FDAT'][0]
    fdat_orig = dat[foff:foff + fsize]
    iv = fdat_orig[-TRAILER:-TRAILER + 16]
    trailer = fdat_orig[-TRAILER + 16:]
    cipher_orig = fdat_orig[:fsize - TRAILER]
    print('FDAT %d = cipher %d + IV 16 + trailer %d' %
          (fsize, len(cipher_orig), len(trailer)))
    print('IV', iv.hex())

    # decrypt via fwtool (read fully -> validates every block checksum)
    crypter, dec = fdat.decryptFdat(io.BytesIO(fdat_orig))
    parts = []
    while True:
        chunk = dec.read(PAYLOAD * 256)   # bounded read; read() alone is quadratic
        if not chunk:
            break
        parts.append(chunk)
    plain = b''.join(parts)
    print('crypter', crypter, 'plaintext', len(plain))

    cipher_new = encrypt_fdat(plain, iv)
    fdat_new = cipher_new + iv + trailer

    off, diff = compare(cipher_new, cipher_orig)
    print('CIPHERTEXT size new=%d orig=%d' % (len(cipher_new), len(cipher_orig)))
    if off is None and len(cipher_new) == len(cipher_orig):
        print('CIPHERTEXT MATCH byte-for-byte (%d bytes, %d blocks)' %
              (len(cipher_new), len(cipher_new) // BLOCK))
    else:
        print('CIPHERTEXT MISMATCH first=0x%x block=%s diffbytes=%d' %
              (off, None if off is None else off // BLOCK, diff))
        if off is not None:
            lo = max(0, off - 16)
            print('  orig', cipher_orig[lo:off + 16].hex())
            print('  new ', cipher_new[lo:off + 16].hex())

    # rebuild DAT: same chunks, FDAT payload replaced, DEND CRC over all before DEND hdr
    _, doff, dsize, dhdr = [c for c in chunks if c[0] == DEND][0]
    rebuilt = bytearray(dat)
    rebuilt[foff:foff + fsize] = fdat_new
    rebuilt[dhdr:dhdr + 8] = struct.pack('>i4s', dsize, DEND)
    crc = zlib.crc32(bytes(rebuilt[:dhdr])) & 0xffffffff
    struct.pack_into('>i', rebuilt, doff, crc)
    print('DEND crc orig=%08x new=%08x' %
          (struct.unpack('>i', dat[doff:doff + 4])[0] & 0xffffffff, crc))

    off, diff = compare(rebuilt, dat)
    print('DAT size new=%d orig=%d' % (len(rebuilt), len(dat)))
    if off is None and len(rebuilt) == len(dat):
        print('DAT MATCH byte-for-byte (%d bytes)' % len(dat))
    else:
        print('DAT MISMATCH first=0x%x (DAT-relative) diffbytes=%d' % (off, diff))
        if off is not None:
            lo = max(0, off - 16)
            print('  orig', dat[lo:off + 16].hex())
            print('  new ', bytes(rebuilt[lo:off + 16]).hex())
            if foff <= off < foff + fsize:
                print('  -> inside FDAT chunk, block %d (block offset %d)' %
                      ((off - foff) // BLOCK, (off - foff) % BLOCK))

    os.makedirs(OUT, exist_ok=True)
    fdat_out = os.path.join(OUT, 'rebuilt_fdat.bin')
    dat_out = os.path.join(OUT, 'rebuilt.dat')
    with open(fdat_out, 'wb') as f:
        f.write(fdat_new)
    with open(dat_out, 'wb') as f:
        f.write(rebuilt)
    print('wrote %s and %s' % (fdat_out, dat_out))


if __name__ == '__main__':
    main()
