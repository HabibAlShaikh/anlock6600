#!/usr/bin/env python3
"""Reproduce the a6600 v1.10 extraction from the official Sony updater.

Requires ma1co/fwtool.py on PYTHONPATH:
    git clone https://github.com/ma1co/fwtool.py
    export PYTHONPATH="$PWD/fwtool.py"

Usage:
    python3 scripts/extract_a6600.py Update_ILCE6600V110.exe out

Offsets below are for the v1.10 updater only. For another version, locate the
FDAT/UFU blob first (fwtool ships readers for DAT/PE containers).
"""

import argparse
import os
import shutil
import subprocess
import sys

UPDATER_BASE = 0xAE9D4      # embedded UFU blob offset
UPDATER_SIZE = 316672424    # embedded UFU blob size


def decrypt(updater_path, out_dir):
    from fwtool.io import FilePart
    from fwtool.sony import dat, fdat

    fdat_path = os.path.join(out_dir, "a6600_fdat.bin")
    with open(updater_path, "rb") as f:
        blob = dat.readDat(FilePart(f, UPDATER_BASE, UPDATER_SIZE))
        crypter, dec = fdat.decryptFdat(blob.firmwareData)
        print(f"crypter: {crypter}")
        with open(fdat_path, "wb") as o:
            shutil.copyfileobj(dec, o)

    with open(fdat_path, "rb") as f:
        h = fdat.readFdat(f)
        print(f"model={h.model:#x} region={h.region:#x} version={h.version}")
        with open(os.path.join(out_dir, "a6600_firmware.tar"), "wb") as o:
            h.firmware.seek(0)
            shutil.copyfileobj(h.firmware, o)
        with open(os.path.join(out_dir, "a6600_updater.img"), "wb") as o:
            h.fs.seek(0)
            shutil.copyfileobj(h.fs, o)


def untar(out_dir):
    fw_dir = os.path.join(out_dir, "firmware")
    os.makedirs(fw_dir, exist_ok=True)
    subprocess.run(
        ["tar", "-xf", os.path.join(out_dir, "a6600_firmware.tar"), "-C", fw_dir],
        check=True,
    )
    return fw_dir


def extract_rootfs(fw_dir, out_dir):
    image = os.path.join(fw_dir, "0700_part_image", "dev", "nflasha15")
    rootfs = os.path.join(out_dir, "rootfs")
    if not os.path.exists(image):
        print("skip rootfs: nflasha15 not found")
        return
    os.makedirs(rootfs, exist_ok=True)
    # ext2 image; debugfs opens read-only unless -w is given.
    # rdump tries to restore root ownership, which fails for non-root users;
    # those warnings go to the log and are harmless.
    with open(os.path.join(out_dir, "debugfs.log"), "w") as log:
        subprocess.run(["debugfs", "-R", f"rdump / {rootfs}", image],
                       check=True, stderr=log)


def extract_system(fw_dir, out_dir):
    image = os.path.join(fw_dir, "0700_part_image", "dev", "nflasha3")
    system = os.path.join(out_dir, "system")
    if not os.path.exists(image):
        print("skip system: nflasha3 not found")
        return
    if shutil.which("7z") is None:
        print("skip system: install p7zip to extract the FAT image")
        return
    os.makedirs(system, exist_ok=True)
    # FAT12 image holding av-cam.bin, vmlinux.bin, initrd.img, ...
    subprocess.run(["7z", "x", "-y", f"-o{system}", image],
                   check=True, stdout=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("updater", help="official Update_ILCE6600V110.exe")
    ap.add_argument("out", help="output directory")
    args = ap.parse_args()

    if not os.path.isfile(args.updater):
        sys.exit(f"not found: {args.updater}")
    os.makedirs(args.out, exist_ok=True)

    decrypt(args.updater, args.out)
    fw_dir = untar(args.out)
    extract_rootfs(fw_dir, args.out)
    extract_system(fw_dir, args.out)
    print(f"done: {args.out}")


if __name__ == "__main__":
    main()
