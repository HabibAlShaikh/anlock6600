# LD_PRELOAD path — running code in `im.elf` without touching `/usr`

Status: **mechanism proven statically, patch proven offline, nothing tested on
hardware.** This is a much smaller install target than a patched
`av-cam.bin`/`libmpr.so` partition image, and it is undone by deleting two text
files and rebooting.

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
ship in `/usr/tool/`. This is a supported internal facility, not a hole we are
opening — the same mechanism is what makes it low-risk to use.

## 4. Why the patch is a byte write, not an interposer

The first attempt was an interposer for the exported symbol in `libmpr.so`
(dynamic symbol table entry `0x0087fdd5`, size 180). It cannot work: **no DSO or
executable in `/usr/lib` or `/usr/bin` references
`_ZN10MprLibCore14GetPictureSizeEN3MPR11VResolutionEPtS2_`** — the only
occurrence is its own definition in `libmpr.so`. Every call is intra-library and
resolves at link time, so `LD_PRELOAD` never gets consulted.

`tools/og.c` therefore patches the instruction in memory:

```
0x87fdd4  MprLibCore::GetPictureSize(VResolution res, u16 *w, u16 *h)   (Thumb)
0x87fe08  4f f4 87 63    mov.w r3, #0x438   ; 1920x1080 case
0x87fe0a  0x87 -> 0xa0   mov.w r3, #0x500   ; 1920x1280
```

The constructor does, in order:

1. `dlsym(RTLD_DEFAULT, …)` — so the patch lands on the `libmpr` instance
   already mapped as an `im.elf` dependency. (Falling back to
   `dlopen("/usr/lib/libmpr.so")` would map a *second* copy and patch nothing
   the camera uses.)
2. Verify all four bytes at `sym + 0x34`. Any mismatch → return without
   writing, so a different firmware build is left untouched.
3. `mprotect` → write `0xa0` at `sym + 0x36` → `__clear_cache` → restore `R|X`.

No allocation, no stdio, no `DT_NEEDED`. Undefined symbols are `dlopen`,
`dlsym`, `sysconf`, `mprotect`, `__clear_cache`; all resolve from `libdl`,
`libc` and `libgcc_s`, which `im.elf` already loads.

## 5. Build and verify

```sh
tools/build_og.sh                                   # -> tools/og.so, ARM EABI5 soft-float
python3 tools/verify_patch.py out/usr/lib/libmpr.so
```

`verify_patch.py` copies `libmpr.so` to a temp directory, checks
`4f f4 87 63` at `0x87fe08`, applies the single-byte edit, and disassembles
both files:

```
before: 0x438 (1080)
after:  0x500 (1280)
ok
```

## 6. Installing it (needs a write path we do not have yet)

The shim itself needs no update container — two files on a vfat partition. But
reaching that partition is the open problem:

1. **Serial shell** — `init` starts a root shell at every boot
   (`docs/uart-shell.md`). This is the shortest route: copy `og.so` to
   `/setting/mode/`, run `change_mode.sh p /setting/mode/og.so`, reboot.
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
4. A broken preload library fails inside `im.elf` startup. Recoverable from the
   serial shell (delete the file) but **not** from the camera UI — see
   `docs/uart-shell.md`.
