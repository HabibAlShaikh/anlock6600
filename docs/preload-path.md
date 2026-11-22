# LD_PRELOAD path — running code in `im.elf` without touching `/usr`

Status: **mechanism proven statically, byte effects proven offline, nothing
tested on hardware.** The shim delivers both halves now: the record table via
a redirected `av-cam.bin` copy, and the encoder size via the patched
`GetPictureSize`. Sensor readout and SPS are still unresolved. Rollback means
restoring `/setting/mode/dmode`, emptying `preload`, removing the library and
`/log/og-av.bin`, and rebooting.

Target: ILCE-6600, firmware **1.10**, ARMv7 / CXD90045.
Evidence: `out/usr/bin/bootin.elf` (13,068 B), `out/usr/bin/change_mode.sh`,
`out/usr/lib/libmpr.so`, `out/firmware/0100_config/mount.conf`.

## 1. What bootin does

`rootfs/sbin/init` → `bootin.elf` → `im.elf`. Before launching `im.elf`, bootin
reads two files from the read-write `/setting` partition (nflasha2, vfat):

| File | Read at | Size | Used for |
|---|---|---|---|
| `/setting/mode/dmode` | `0x923e` `open()`, `0x924a` `read()`, path `0x9e2b` | 30 B | flag characters |
| `/setting/mode/preload` | `0x9752` → reader `0x9018` | 1024 B | `LD_PRELOAD` value |

`0x9018` opens the preload file and copies its contents into the command buffer
at `.data` `0x1297c`, prefixed with `LD_PRELOAD="` (literal `0xa144`) and closed
with `" ` (literal `0xa151`). Bootin then appends `im.elf ` (`0xa2bd`), option
words such as `lazy-global ` (`0xa2e5`), and `& ` (`0xa2f2`), and runs the
result with `system()` at `0x982e`.

So the effect is a **shell prefix assignment**, not an exported variable:

```
LD_PRELOAD="/setting/mode/og.so" im.elf … lazy-global &
```

The `putenv("LD_PRELOAD")` at `0x9860` runs *after* `system()` returns and is
cleanup ("Bb clearing env"), not the injection point.

## 2. Parsing `/setting/mode/dmode`

`0x9210` reads the file and walks it byte by byte (`0x9256`–`0x92c0`), OR-ing
bits into a global flag word. Every case verified in the disassembly:

| Characters | Address | Result |
|---|---|---|
| `0` `1` `2` `3` | `0x9258`–`0x9266` | select one of four stored path strings (`0x945c`–`0x9468`) |
| `p` `P` | `0x9268`–`0x9270` | `flags |= 0x40` — **read `/setting/mode/preload`** |
| `l` `L` | `0x9276`–`0x927e` | `flags |= 0x42` |
| `w` `W` | `0x9284`–`0x928c` | `flags |= 0x08` |
| `g` `G` | `0x9292`–`0x929a` | `flags |= 0x10` (`daemon()`) |
| `s` `S` | `0x92a0`–`0x92a8` | `flags |= 0x20` |

`0x9746` tests `#0x40`; without it the preload file is ignored entirely. The
same parser also accepts argv forms (`dmode=`, `amode=`, `file=`, `target=`,
`sim`, `lt`, `wfree`, `gdbs`) at `0x92d0`–`0x94c0`, but `init` passes no
arguments to bootin.

## 3. Sony ships a tool for this

`/usr/bin/change_mode.sh` is a vendor debug helper that writes exactly these
two files:

```sh
change_mode.sh p /setting/mode/og.so     # echo 3p > dmode; echo -n <path> > preload
```

Other documented modes use the same hook: `7` preloads `LeakTracer.so`, `f`
preloads `libjemalloc_tsh.so`, `10` preloads `libmcheckb.so`. Those libraries
ship in `/usr/tool/`. The facility is vendor-supported, but it is still
arbitrary code in `im.elf`: a faulty library can hang startup, and the "debug"
label is not a safety guarantee.

## 4. Why the patch is a byte write, not an interposer

The first attempt was an interposer for the exported symbol in `libmpr.so`
(dynamic symbol table entry `0x0087fdd5`, size 180). It cannot work here: **no
dynamic reference to
`_ZN10MprLibCore14GetPictureSizeEN3MPR11VResolutionEPtS2_` exists outside
`libmpr.so`** in `/usr/lib` or `/usr/bin`; the only occurrence found is its own
definition. The observed callers are intra-library, so `LD_PRELOAD` is never
consulted for that name.

`tools/og.c` therefore patches the instruction in memory:

```
0x87fdd4  MprLibCore::GetPictureSize(VResolution res, u16 *w, u16 *h)   (Thumb)
0x87fe08  4f f4 87 63    mov.w r3, #0x438   ; 1920x1080 case
0x87fe0a  0x87 -> 0xa0   mov.w r3, #0x500   ; 1920x1280
```

The two hooks, in the order they fire:

1. `syscall(0x80, …)` — `im.elf` builds `fn=/system/av-cam.bin …` in a
   0x400-byte buffer (`0xb32e`) and loads `liro.ko` (`0xb2d0`). The hook
   rewrites `fn=` to a verified patched copy (`docs/patch-map.md` §6).
2. `dlopen()` — `libmpr.so` is **not** a startup dependency of `im.elf`;
   nothing lists it in `DT_NEEDED`. `im.elf` loads it later through
   `libIMDB.so`'s module table, possibly transitively (`libObj.so` does
   `NEED` it). The hook records the first handle whose scope defines
   `GetPictureSize`, and patches only once the `fn=` redirect succeeded:
   verify the four bytes at `sym + 0x34` (any mismatch → leave the build
   untouched), `mprotect` (two pages: the instruction may straddle a page
   boundary), write `0xa0` at `sym + 0x36`, `__clear_cache`, restore `R|X`.

The shim never calls `dlopen()` itself, so it cannot change the camera's
load order. No allocation, no stdio, no `DT_NEEDED`. Undefined symbols are
`open, close, fstat, pread, strncmp, strlen, memmove, dlsym, sysconf,
mprotect, __clear_cache`; all resolve from `libdl`, `libc` and `libgcc_s`,
which `im.elf` already loads.

## 5. Build and verify

```sh
tools/build_og.sh                                   # host fn= test, then -> og.so (armv7 EABI5)
python3 tools/verify_patch.py  out/usr/lib/libmpr.so
python3 tools/verify_record.py out/system/av-cam.bin
```

`verify_patch.py` checks the pinned SHA-256, the dynamic symbol value/size, the
ELF VA→file mapping and `4f f4 87 63` at `0x87fe08`, then copies `libmpr.so` to
a temp directory, applies the single-byte edit, asserts that exactly one byte
changed, and disassembles both files:

```
before: 0x438 (1080)
after:  0x500 (1280)
ok
```

## 6. Installing it (needs a write path we do not have yet)

The shim itself needs no update container — the library plus two text files on a
vfat partition. But reaching that partition, and making the rest of the pipeline
agree, are separate problems:

> **Do not install `og.so` as an open-gate test on its own.** It now delivers
> both halves (record 822 via the redirected copy, encoder via the patched
> `GetPictureSize`), but the sensor readout at 3:2/24p and the H.264 SPS/level
> are unproven, and the redirect has never run on hardware. The result may be
> no effect, a failed recording, a corrupt file, or an application crash.

1. **Serial shell** — `init` unconditionally attempts to start `/bin/ash` on a
   console (`docs/uart-shell.md`). If that is usable, it is the shortest route:
   copy `og.so` to `/setting/mode/`, run
   `change_mode.sh p /setting/mode/og.so`, reboot. Prove rollback first.
2. **Official update** — the payload carries `0800_appli/{setting,tmp,lens}` and
   verifies the installed partition against `0801_appli_sum/appli.sum`
   (`us_crc32sum_appli.sh`). Sum format:

   ```
   type,crc32,size,mode,0,1000,root,root,-1,-1,path,
   ```

   `type` is 0 for a file and 5 for a directory (`ffffffff`, size 0); `crc32` is
   zlib CRC-32 (verified against `config.sum`). Adding `setting/mode/` plus two
   files means three new lines and a repacked FDAT; the container rebuild is
   already byte-proven (`research/scripts/fdat_roundtrip.py`).

## 7. Open items

1. The a6600 payload has no `nflasha2` image, and `uc_mkfs.elf` only runs
   `mkdosfs` on nflasha1/2/13. The step that copies `0800_appli/setting/*` onto
   the partition is not identified, so the update route cannot yet be shown to
   create a **new** `mode/` subdirectory.
2. FDAT 256-byte trailer acceptance is unresolved (`docs/install-path.md` §4).
   Do not flash on this document alone.
3. `og.so` changes the `#0x438` immediate shared by code 1 (1440×1080), so that
   slot also becomes 1440×1280. Harmless for a first proof; a code-2-only patch
   needs a code cave.
4. A broken preload library fails inside `im.elf` startup. Recoverable only if
   the serial console is interactive and `/setting` remains mountable; it is
   **not** recoverable from the camera UI — see `docs/uart-shell.md`.
5. **Record delivery.** Implemented in `tools/og.c`: the `syscall(128)` hook
   rewrites `fn=` to a verified patched copy, and the `dlopen` hook patches
   the encoder only after that load succeeded (`docs/patch-map.md` §6).
   Unproven on hardware: that `liro` accepts the redirected path at boot, and
   how a 16.8 MB copy can be placed on `/log` without a root shell.
6. **Observability.** `og.so` exits silently on every failure path and has no
   success marker. A stock-looking result cannot be distinguished from a failed
   load, a failed `mprotect`, or an unused patch. A no-op preload probe with an
   observable result is a prerequisite for interpreting hardware tests.
