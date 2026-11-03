# Install path (G0) — can a modified a6600 firmware be installed?

Status: **unresolved, fail-closed — but no cryptographic verifier was found in any
extractable update code.** The 256-byte FDAT trailer is still unexplained, and the
loader/ROM is not available for inspection. No camera write, flash or service
command has been sent.

Target: ILCE-6600, firmware **1.10** (`38114_02.2020071501`), ARMv7 / CXD90045.
Input: official `Update_ILCE6600V110.exe`.

Reproduce the container facts with:

```sh
python3 research/scripts/inspect_updater.py Update_ILCE6600V110.exe
```

## 1. The update chain

```
PC (Update_ILCE6600V110.exe)
 └─ DAT container  \x89UFU\r\n\x1a\n, chunks DATV/PROV/UDID/FDAT/DEND
     └─ FDAT  ciphertext(316,672,000 B) + IV(16 B) + trailer(256 B)
         └─ plaintext  header "UDTRFIRM" + tar
             ├─ 0100_config/…             mount.conf, big_backup.conf
             ├─ 0300_partconf/partinf.conf
             ├─ 0700_part_image/dev/…     nflasha3, nflasha5, nflasha7, nflasha15
             ├─ 0800_appli/…              /setting and /lens overlay
             └─ …_sum/*.sum               per-file CRC32 lists
```

Measured on the v1.10 file:

| Item | Value |
|---|---|
| DAT offset / size | `0xAE9D4` / 316,672,424 |
| DAT CRC32 | stored `0x157d2ed5` = computed (covers all bytes before the DEND header) |
| FDAT chunk | 316,672,272 bytes at `0xAEA60` |
| FDAT ciphertext | 316,672,000 bytes (multiple of 1024) |
| FDAT IV | `18978e78670d9ab547012a9622682b4b` |
| FDAT trailer | 256 bytes, 255 non-zero, `sha256 cecb491b…615b6700` |

The plaintext payload is **not** per-file signed or encrypted: `av-cam.bin` is a
raw ARM image (`ORIL`), `nflasha7`/`nflasha15` are plain ext2 and `nflasha3` is a
plain FAT image.

## 2. What each layer checks

| Layer | Protection actually found | Evidence |
|---|---|---|
| PC updater self-check | Authenticode on the `.exe` only; no firmware crypto | PE delay imports `WinVerifyTrust`, `CryptQueryObject`, … |
| DAT container | CRC32 (`DEND`) | `crypter.elf` `CrcChecker` 0xadfc/0xae60; verified |
| UFP receive | none; writes `/tmp_updater/Firm.dat` | `libupdaterufp.so` 0x1622–0x1660 |
| FDAT wrapper | AES with a hard-coded key; container rebuildable byte-for-byte (round-trip proven) | `libupdatertalk.so` `Dec_Scramble`; `research/scripts/fdat_roundtrip.py` |
| FDAT trailer | **never read** by any extractable update code; copied verbatim on rebuild | see §3.1 |
| Update body | CRC32 sums driven by its own `config.xml` | `libupdaterbody.so` `GetBody` 0xfa85 |
| Partition images | none beyond the above | `us_mkfs.sh`, `loader_writer.sh` |
| Boot of `/usr`, `/rootfs`, `/system` | no verity/IMA/signature found | `vmlinux.bin` string scan |

## 3. The camera-side path is fully visible — and CRC-only

The update runs in the normal OS, not from a separate updater partition:

1. `usr/bin/im.elf` (`DT_NEEDED libIMDB.so`) loads `libIMDB.so`.
2. `libIMDB.so` has a module table entry `"libupdaterufp.so", "udtr_ufp_init",
   "udtr_ufp_exit"` (offset `0x4d39`) and `dlopen`s it.
3. `libupdaterufp.so` receives the file, mounts a work area and writes
   `/tmp_updater/Firm.dat` (`0x1622–0x1660`). It verifies nothing.
4. It calls `system("crypter.elf /tmp_updater/Firm.dat")` (`0x16e8`), then
   `up.sh ver` or `up.sh user` (`0x1990`, `0x19dc`).
5. `crypter.elf` walks the `\x89UFU` chunk list (`0xb2a0–0xb3fc`), finds `FDAT`,
   and runs `CrcChecker` over the whole container up to `DEND` (`0xadfc–0xaed6`,
   `memcmp` of the `DEND` tag and a CRC32 compare). No other integrity check.
6. `crypter.elf` decrypts with `Dec_Scramble` and writes the body image to
   `/tmp_updater/updater/bodyimg`, skipping a 0x200-byte header (`0xc040–0xc112`).
7. It loop-mounts `bodyimg` as cramfs at `/tmp_updater/updater/bodyfs`
   (`0xc4c2–0xc4ee`) and `dlopen`s
   `bodylib/libupdaterbody.so` (`0xc516`), unless `/root/IAMUPDATER` exists, in
   which case it uses the built-in `/usr/bin/udtrbody.bin` instead.
8. `libupdaterbody.so` unpacks to `/tmp_updater/updater/update` and runs the
   `config.xml` scripts (`chkfirm.sh`, `us_crc32sum*.sh`, `uc_mkfs.elf`,
   `edisx.elf`, `ud_wbi_drop.elf`, …), which check per-file CRC32 sums.

Consequences:

- The body that validates the payload is supplied **by the payload** and is
  covered only by the payload's own CRC lists → the CRC layer is not a security
  boundary against someone who rebuilds the container.
- `crypter.elf` mounts `/dev/nflasha2` and then `/dev/nflasha1` only to read
  `dat2` (model), `dat3` (region) and `updater/dat4` (version) at `0xd6d4`/
  `0xd750`. They are not a verifier.

## 3.1 The container is rebuildable offline

`research/scripts/fdat_roundtrip.py` decrypts the FDAT, re-encrypts the same
plaintext, rebuilds the DAT, and matches the official file **byte-for-byte**
(316,672,424 bytes, DEND CRC `0x157d2ed5`). Confirmed framing:

- 309,250 blocks × 1024 bytes; each block starts with `u16le checksum` +
  `u16le (size | 0x8000 end flag)` + payload + `0xff` padding.
- Checksum = sum of the 511 little-endian u16 words of bytes 2..1023.
- First block: first 512 bytes AES-**ECB** with `key_aes`, remaining 512 AES-CBC
  with `key_cxd90045` chained from the stored IV; later blocks are full CBC and
  the chain carries across blocks.
- IV sits at `len - 0x110`; the 256-byte trailer follows it and is copied
  verbatim.

This means the encryption layer is solved. It does **not** prove that a modified
container is accepted: if the 256-byte trailer signs the plaintext, changing a
payload byte invalidates it even though no visible code checks it.

## 4. The 256-byte trailer

No extractable update component reads it:

| File | EOF/trailer behaviour |
|---|---|
| `libupdaterufp.so` | only `lseek(fd,0,SEEK_END)` for file size (`0x1d16`); reads 4/2-byte fields; no last-0x100 read |
| `crypter.elf` | reads 4-byte chunk lengths and the 12-byte `DEND`; no seek-to-EOF-minus-N, no 0x100/0x110 constant |
| `libupdaterbody.so` | forward-only extraction; no `SEEK_END`, no negative offset |
| Update scripts/ELFs | CRC32 only |
| PC updater | no firmware crypto at all |

A scan of 48 update-path files found **zero** PEM/DER/RSA public keys and no
`RSA_verify`/`EVP_DigestVerify` imports outside the TLS stack (`libcrypto`,
`libssl`, `wpa_supplicant`, `orb-server`). The only crypto primitive in the
update path is symmetric AES with a hard-coded key in `libupdatertalk.so`.

**Inference:** if the 256-byte trailer is enforced, the check is outside the
extractable code (loader/ROM or a closed service). It is not what
`crypter.elf`/`libupdaterbody.so` check.

## 5. Boot-time verification

Nothing indicates that `/usr` (`nflasha15`), `/rootfs` (`nflasha7`) or `/system`
(`nflasha3`) is verified at boot:

- `vmlinux.bin` has no `dm-verity`, IMA, module-signature or secure-boot strings.
- `rootfs/sbin/init` has **no updater branch** (`IAMUPDATER`, `/tmp_updater`,
  `udtrbody`, `crypter`, `up.sh` all absent). It mounts the partitions and runs
  `bootin.elf` → `im.elf`.
- `usr/bin/bootin.elf` launches `im.elf`, reads `/setting/mode/dmode` and
  `/setting/mode/preload`, and verifies nothing (no CRC/hash imports).
- `/usr` and `/rootfs` are mounted **read-only** (ext2/cramfs paths); `/setting`
  is rw vfat.

Absence of evidence, not proof: the loader (`nflashaB0`) and ROM were not
available.

## 6. Revised G0 verdict

**G0: unresolved, fail-closed.** The prior claim that "Gen4 signature
verification blocks modified updates" is **overstated**: no verifier exists in
the entire extractable update path, and the trailer is never read by it. What
remains is one unexplained 256-byte block and an uninspectable loader/ROM.

The install path is therefore **plausibly open but unproven**. The remaining
work is delivery plus one unknown:

1. ~~Rebuild the DAT/FDAT~~ — **done offline** (`fdat_roundtrip.py`, byte-identical,
   §3.1). Recompute every `*_sum/*.sum` CRC32 after changing a payload file.
2. Deliver it: a custom UFP sender, or the stock exe with its Authenticode
   self-check removed.
3. Prove acceptance on a sacrificial unit with a **byte-identical repack** first
   (same firmware, recomputed container). An accepted repack proves the trailer
   is not enforced without changing camera functionality; a rejected one should
   abort before any write.

Do not flash the user's camera on this evidence. A hardware acceptance test is a
separate, explicitly approved action.

## 7. Preconditions before the first write

1. ~~Offline repack tool with a decrypt→encrypt round-trip~~ — **done**, matches
   the original container byte-for-byte.
2. A full dump of `nflasha1`, `nflasha2`, `nflasha3`, `nflasha5`, `nflasha7`,
   `nflasha15`, `nflashaB0`, with hashes.
3. A **tested** restore of that dump to the same unit.
4. A sacrificial unit or a service option, if the restore is not proven.
5. A UFP sender or a patched exe, tested against the camera's USB descriptors
   without sending firmware.

## 8. Claims corrected in this pass

- "Gen4 FDAT signature verification blocks modified updates" → **not
  supported** by the extractable code. No verifier found; the trailer is not
  read. Enforcement, if any, is outside the visible path.
- "The verifier lives in `nflasha1`" → **wrong**. `nflasha1`/`nflasha2` are
  mounted to read `dat2`/`dat3`/`dat4` (model/region/version), not to verify.
- "The 256-byte block is an RSA signature" → still plausible (size/entropy), but
  unproven and not read by any extracted component.
- "The update runs from a separate updater partition" → **wrong for this path**.
  It runs from the normal OS via `im.elf → libIMDB → libupdaterufp → crypter`.

## 9. Open questions

- Is the trailer checked by the loader/ROM, or is it vestigial?
- Can the stock `.exe` be used after defeating its Authenticode self-check, or is
  a UFP protocol reimplementation required?
- Does an interrupted update leave a recoverable state? (The update writes
  partitions in place; no atomic A/B slot was found.)
