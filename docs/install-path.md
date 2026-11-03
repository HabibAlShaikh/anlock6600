# Install path (G0) — can a modified a6600 firmware be installed?

Status: **unresolved, fail-closed.** This document maps what the stock update
actually verifies and where. No camera write, flash or service command was sent.

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
plain FAT image. Everything that protects them sits in the FDAT wrapper.

## 2. What each layer actually checks

| Layer | Protection | Who checks | Evidence |
|---|---|---|---|
| DAT chunks | CRC32 (`DEND`) | PC updater / receiver | `fwtool/sony/dat.py`; verified above |
| FDAT header | CRC32 over the header (`FdatHeader.checksum`) | receiver | `fwtool/sony/fdat.py:256` |
| FDAT body | AES-CBC with **fixed, public** keys + 16-byte IV + 256-byte trailer | receiver | `fwtool/sony/constants.py`; trailer layout below |
| Payload files | per-file CRC32 + size in `*_sum/*.sum` | update body on camera | `uc_crc32sum.elf -c`, `config.xml` |
| Partition images | none beyond the above | raw write | `us_mkfs.sh`, `loader_writer.sh` |
| Boot of `/usr`, `/rootfs`, `/system` | no verity/IMA/signature found | kernel/userland | `system/vmlinux.bin` string scan |

Key detail: `fwtool` decrypts Gen4 (`CXD90045`) but **refuses to encrypt**
(`AesCbcCrypter.encrypt` raises `Encryption not supported`). The reason is the
trailer: `[ciphertext][16-byte IV][256-byte block]`, which is consistent with an
RSA-2048 signature over the payload. A 256-byte high-entropy block is not a CRC,
not an AES IV and not a symmetric MAC.

## 3. Where the verifier is not

The update body on the camera is `out/a6600_updater.img` — a 47-file CRAMFS also
shipped as `usr/bin/udtrbody.bin`. Its scripts and ELFs check **only** CRC32:
`config.xml` drives `us_crc32sum*.sh` → `uc_crc32sum.elf` /
`ul_crc32sumprfile.so`, then `edisx.elf` / `uc_mkfs.elf` / `ud_wbi_drop.elf`
write partitions. There is no asymmetric crypto, certificate or signature string
in any of those files.

The camera-side updater code reachable in this payload is also decrypt-only:

| File | Relevant symbols / strings |
|---|---|
| `usr/bin/crypter.elf` | `Dec_Scramble(Init)`, `Fsys_*`, `CrcChecker.cpp`, `calc_crc` |
| `usr/lib/libupdaterufp.so` | UFP receive path, `Dec_Scramble(Init)`, `udtr_*`, `set_model/region/version` |
| `usr/lib/libupdatertalk.so` | `AES_set_decrypt_key`, `AES_decrypt` |
| `usr/lib/libupdatercommon.so` | file/FS plumbing, `memcmp`, `dlopen` |

None of them imports `RSA_verify`, `EVP_DigestVerify`, `SHA256_*` or any other
signature primitive. `libcrypto.so` on the camera is the normal TLS stack.

**Inference:** if the 256-byte trailer is enforced, the verifier lives outside
this update payload — most likely in the persistent updater partition
`/dev/nflasha1` ("SYSTEM (Updater)", 8 MB vfat, `mount.conf`), which this update
does not rewrite, or in boot ROM. That partition is not in the extracted tree
because Sony does not ship it in `firmware.dat`.

## 4. Boot-time verification of the partitions we would patch

Nothing indicates that `/usr` (`nflasha15`, raw ext2), `/rootfs` (`nflasha7`,
raw) or `/system` (`nflasha3`, vfat) is verified at boot:

- `vmlinux.bin` has no `dm-verity`, `IMA`, module-signature or secure-boot
  strings; the custom `ssboot/image.c` code only loads images.
- `/setting` (`nflasha2`, writable vfat) is read at boot by `rootfs/sbin/init`:
  it consumes `/setting/env.txt` and `/setting/mode/dmode`, and
  `usr/bin/change_mode.sh` writes `/setting/mode/preload` for an
  `LD_PRELOAD`-style library.
- `rootfs/sbin/init` contains a `launch_shell()` path for
  `/usr/bin/launch_shell.elf`, which opens `/dev/ttycons` or `/dev/console` and
  execs `/bin/ash`; the kernel command line uses `console=ttyAM0`. A UART shell
  is therefore a plausible runtime path (hardware access required, not tested).
- `/wbi` (`nflasha5`) is a separate compressed warm-boot blob, mounted as a
  filesystem entry (`mount.conf` type `wbi`), not the source of `/usr`.

This is absence of evidence, not proof of no verification. A boot-time check
could still exist in the loader or in `nflasha1`.

## 5. Alternative install paths

| Path | Status | What would settle it |
|---|---|---|
| A. Modified official update | **Blocked (likely)** by the 256-byte FDAT trailer. Re-encryption is implementable (AES-CBC, public keys) but the trailer cannot be regenerated without Sony's private key. | Dump `nflasha1`, find the FDAT verifier, confirm whether the trailer is checked. If it is not, A becomes viable. |
| B. Runtime shell / write to `/usr`, `/rootfs` or `/setting` | **Unknown, plausible.** `init` starts `launch_shell.elf` on `ttyAM0` and reads `/setting/env.txt`; `/usr` is mounted from ext2/cramfs/vfat. | Locate UART pads, confirm the shell is enabled, check whether `/usr` is mounted rw. A shell would allow a reversible runtime patch without touching the signed update path. |
| C. Hardware NAND write | **Unknown, high risk.** Requires a full dump and a loader that does not verify. | Identify the NAND part, dump all partitions, compare the loader against `nflasha1`. |
| D. Network exploit (`orb-server`, web API) | **Out of scope.** A separate vulnerability project with poor reliability. | Only with a tested restore path. |

Path B is the only one that could work without breaking the signature, and it is
the one this project should price first: the camera already has the debug hooks,
and `/setting` is a plain writable FAT partition.

## 6. G0 verdict

**G0: FAIL (unresolved).** The stock update is CRC-checked and encrypted with
public keys, but the Gen4 FDAT wrapper carries a 256-byte block that is
consistent with a signature, and `fwtool` cannot reproduce it. The verifier is not
in the update payload, so enforcement cannot be proven or disproven from the
files we can extract.

Do not patch and flash on this evidence. The next concrete step is a read-only
dump of `nflasha1` (and the loader area `nflashaB0`) to locate the FDAT verifier,
followed by the runtime-access investigation (path B). Both are prerequisites for
any write.

First actions, in order:

1. Dump `nflasha1` and `nflashaB0`; hash them and look for an RSA/ECDSA verify
   routine or a public key in the updater OS.
2. Inspect the mainboard for `ttyAM0`/`/dev/ttycons` test points and confirm
   whether `launch_shell.elf` is reachable (read-only boot observation).
3. Only if 1 or 2 succeeds, build the recovery path (§7) before touching a
   movie table.

## 7. Preconditions before the first write

1. Full dump of at least `nflasha1`, `nflasha2`, `nflasha3`, `nflasha5`,
   `nflasha7`, `nflasha15` and `nflashaB0`, with hashes.
2. A **tested** restore of that dump to the same unit.
3. A second unit, or a service option, if the first restore is not proven.
4. Bench setup: charged battery or dummy battery, SD card, room temperature.
5. The patch is limited to one movie format slot and is reversible by flashing
   the stock v1.10 payload again.

## 8. Open questions

- Is the 256-byte trailer an RSA signature, and which key verifies it?
- Does `nflasha1` contain the verifier, and is it reachable from the running OS?
- Is `/usr` mounted read-only, and does anything hash it at boot?
- Does `/wbi` cache any of `/system` or `/usr`, so a patched file would be
  shadowed until the WBI is regenerated?
- Can `/setting/mode/preload` be written through any exposed interface?
