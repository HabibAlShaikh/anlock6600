# Serial root shell — what the firmware already does

Status: **proven from the binaries, untested on hardware.** The boot path starts
an unauthenticated root shell on the serial console at every power-on. This is
the recovery path for every experiment in this repository, and the shortest way
to get files onto `/setting`.

Target: ILCE-6600, firmware **1.10**, ARMv7 / CXD90045.
Evidence: `out/rootfs/sbin/init` (27,006 B), `out/usr/bin/launch_shell.elf`
(5,092 B).

## 1. The call chain

```
rootfs/sbin/init  main
  0x9b2e:  bl 0x9620            ; launch_shell()  — no branch guard
  0x9620:  launch_shell
    0x9676:  execl("/usr/bin/launch_shell.elf",
                   "/usr/bin/launch_shell.elf", arg1, arg2, NULL)
```

`launch_shell` (`0x9620`) formats two 2-byte strings with `snprintf("%s")`
(literal `0xa081`) from globals at init `.data` `0x144dc` / `0x144e0`, each
rendered as `"0"` (`0xa6ee`) or `"1"` (`0xa6ad`), then calls `execl` at `0x9676`
with the path at `0xa348`. If `execl` fails, main logs
`launch_shell() failed` and continues.

There is no test for a gate file, no password, and no hardware check between
`main`'s fall-through at `0x9b2a` and the call at `0x9b2e`: every path through
`main` reaches it.

Order inside `main`:

```
0x9af2  system("/usr/bin/bootin.elf")      ; or 0x9af8 run_bg_process(...)
0x9b1e  mount_partition(...)
0x9b24  putenv("LD_PRELOAD=")              ; literal 0xa80d — clears it
0x9b2a  profile_exit()
0x9b2e  launch_shell()
```

`bootin` is started first and detaches (`im.elf … &`), so the shell comes up
while the application is still booting — available even when `im.elf` fails.
`putenv("LD_PRELOAD=")` at `0x9b24` strips any inherited preload before the
handover, so the shell itself always runs clean.

If `execl` fails, `launch_shell` returns and `main` logs
`launch_shell() failed` (`0x9b3e`) and then loops
`system("/bin/ash --login")` forever (`0x9b42` → `0x9b48`) — a second,
independent attempt on init's own stdio.

## 2. What launch_shell.elf does

Function `shell_loop` (`0x8a64`; the name comes from its `shell_loop:` error
format at `0x8b16`) selects a device and hands over to `/bin/ash`:

```
0x882c  ldr  r3, [r5]          ; flag from argv
0x8830  /dev/ttycons           ; flag == 0   (literal 0x8b30)
0x8838  /dev/console           ; flag != 0   (literal 0x8b3d)
0x8840  open(dev, O_RDWR)
0x8866  dup2(fd, 0)            ; stdin
0x886e  dup2(fd, 1)            ; stdout
0x8876  dup2(fd, 2)            ; stderr
        execv("/bin/ash", …)
```

No credential check exists in the binary; the only strings it uses are the two
device paths, `/dev/ram0`, `/bin/ash` and the error formats.

The kernel command line in `init` sets `console=ttyAM0`, so `/dev/console` is the
SoC UART and `/dev/ttycons` is the same console from the application side.

## 3. Consequences

1. **Recovery is possible for every change in this repo.** A broken
   `LD_PRELOAD` library, a bad `/setting` file or a blocked `im.elf` can be
   undone from the shell: mount (or `rm` from) `/setting` and reboot.
2. **Partition backups become possible** before any risky step — dump
   `/dev/nflasha*` to the SD card.
3. **No firmware update is needed to place a file in `/setting`** once the shell
   is reachable, which removes the FDAT-trailer problem from the critical path.
4. The shell is started after `bootin`, but `bootin` backgrounds `im.elf`, so the
   shell is reachable while the application is still starting — including when
   `im.elf` dies. Confirm the timing from a live boot log.

## 4. What is still unknown

| Item | Status |
|---|---|
| Physical test points on the A6600 mainboard | unknown — needs service manual or a teardown |
| Logic level | assume 3.3 V TTL; **measure before connecting** |
| Baud rate | start at 115200 8N1; `init` does not set it, the kernel default applies |
| Whether `ttyAM0` is exposed as a pad or only through the USB/service connector | unknown |

## 5. Test protocol (read-only first)

1. Open the body, locate three pads (TX, RX, GND) near the SoC or the service
   connector. Photograph the board and label the pads before probing.
2. With the camera **off**, measure resistance from each candidate pad to a
   known ground and to the battery positive. A pad at 0 Ω to ground is GND.
3. Power on **with the probe disconnected** and measure DC on the suspected TX
   pad: a UART idles high, at the I/O rail voltage (3.3 V typical).
4. Connect only GND and RX (camera TX → adapter RX) at 115200 8N1 and capture
   the boot log. Do not connect adapter TX yet.
5. Only after a clean log is captured, connect TX and confirm a prompt appears.
6. First session, all read-only: `id`, `cat /proc/cmdline`, `mount`, `ls -l
   /setting/mode`, `cat /setting/mode/dmode`, `dmesg | tail`.
7. Then dump partitions to SD before changing anything:
   `dd if=/dev/nflasha15 of=/mnt/sd/nflasha15.bin bs=1M`.

Do not send `change_mode.sh`, write `/setting`, or touch `/dev/nflasha*` until
the backup in step 7 is verified by size and hash.

## 6. Why this matters for the goal

`docs/preload-path.md` describes a two-file, reboot-reversible change that
patches the 1080p encoder size to 1920×1280. The only missing piece is a way to
write those two files. The serial shell is that way, and unlike the update route
it needs no container rebuild, no trailer explanation and no flash.
