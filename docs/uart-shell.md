# Serial console — the shell launch the firmware attempts

Status: **unconditional shell launch attempt found statically; no hardware
validation.** The boot path tries to exec `/bin/ash` on a console device at every
power-on. Whether that console is physically reachable, accepts input, or
survives an `im.elf` failure is unproven. If it does work, it is the recovery
path for preload experiments and the shortest way to get files onto `/setting`.

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

`bootin` is started first and detaches (`im.elf … &`), so if the console works it
should come up while the application is still booting — including when `im.elf`
dies. This ordering is static inference; confirm it from a live boot log.
`putenv("LD_PRELOAD=")` at `0x9b24` strips any inherited preload before the
handover, so the shell itself should run clean.

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

The kernel command line is expected to use `console=ttyAM0`; `init` contains
that literal, but the actual `/proc/cmdline`, device nodes and physical mapping
must be confirmed on hardware. Treat `/dev/console` = SoC UART as an inference,
not a fact.

## 3. Consequences if it works

1. **Rollback becomes possible for preload and `/setting` changes.** A broken
   preload library or bad `/setting` file can be undone from the shell: restore
   `dmode`, empty `preload`, delete the library, reboot. It does not make an
   arbitrary flash or partition write safe.
2. **Partition backups become possible** before any risky step — read
   `/dev/nflasha*` to an SD card and verify hashes on both sides.
3. **No firmware update is needed to place a file in `/setting`** once the shell
   is interactive, which removes the FDAT-trailer problem from that route.
4. The shell is started after `bootin`, but `bootin` backgrounds `im.elf`, so it
   should be reachable while the application is still starting. Confirm the
   timing from a live boot log.

## 4. What is still unknown

| Item | Status |
|---|---|
| Physical test points on the A6600 mainboard | unknown — needs service manual or a teardown |
| Whether the boot shell is reachable and interactive | unknown — static call site only |
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
7. Before changing anything, enumerate devices (`ls -l /dev/nflasha*`,
   `cat /proc/partitions`, `mount`, `df -h`) and check free SD space. Dump the
   critical partitions, then hash them on camera and host:

   ```sh
   dd if=/dev/nflasha2  of=/mnt/sd/nflasha2.bin  bs=1M
   dd if=/dev/nflasha15 of=/mnt/sd/nflasha15.bin bs=1M
   sync
   sha256sum /mnt/sd/nflasha2.bin /mnt/sd/nflasha15.bin
   ```

   A `dd` exit status alone is not a verified backup.

Do not send `change_mode.sh`, write `/setting`, or touch `/dev/nflasha*` until
the backup files have correct sizes and hashes, and until a harmless
`/setting/mode/` create-delete-reboot drill has passed.

## 6. Why this matters for the goal

`docs/preload-path.md` describes a small, reboot-reversible change that patches
the 1080p encoder size to 1920×1280. The serial shell would provide a way to
write those files without a firmware update, but the record table, sensor
readout and SPS still have to agree. The shell is necessary, not sufficient.
