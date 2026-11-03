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
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

UPDATER_BASE = 0xAE9D4      # embedded UFU blob offset
UPDATER_SIZE = 316672424    # embedded UFU blob size
EXPECTED_MODEL = 0x81030014
EXPECTED_VERSION = "1.10"


def check_deps():
    try:
        import Cryptodome  # noqa: F401
    except ImportError:
        sys.exit("missing pycryptodomex: python3 -m pip install pycryptodomex")
    try:
        import fwtool  # noqa: F401
    except ImportError:
        sys.exit(
            "missing fwtool: git clone https://github.com/ma1co/fwtool.py "
            'and export PYTHONPATH="$PWD/fwtool.py"'
        )
    for cmd in ("tar", "debugfs", "7z"):
        if shutil.which(cmd) is None:
            sys.exit(f"missing tool: {cmd} (install it and retry)")


def reset(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def decrypt(updater_path, out_dir):
    from fwtool.io import FilePart
    from fwtool.sony import dat, fdat

    if os.path.getsize(updater_path) < UPDATER_BASE + UPDATER_SIZE:
        sys.exit(f"{updater_path} is too small for the v1.10 updater layout")

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
        if h.model != EXPECTED_MODEL or h.version != EXPECTED_VERSION:
            sys.exit("unexpected firmware: expected a6600 v1.10, stopping")
        with open(os.path.join(out_dir, "a6600_firmware.tar"), "wb") as o:
            h.firmware.seek(0)
            shutil.copyfileobj(h.firmware, o)
        with open(os.path.join(out_dir, "a6600_updater.img"), "wb") as o:
            h.fs.seek(0)
            shutil.copyfileobj(h.fs, o)


def untar(out_dir):
    fw_dir = os.path.join(out_dir, "firmware")
    reset(fw_dir)
    subprocess.run(
        ["tar", "-xf", os.path.join(out_dir, "a6600_firmware.tar"), "-C", fw_dir],
        check=True,
    )
    return fw_dir


def extract_ext2(image, target, log_path):
    if " " in os.path.abspath(target):
        sys.exit("output path must not contain spaces (debugfs limitation)")
    reset(target)
    # debugfs opens read-only unless -w is given. rdump tries to restore root
    # ownership, which fails for non-root users; those warnings go to the log.
    with open(log_path, "w") as log:
        subprocess.run(
            ["debugfs", "-R", f"rdump / {target}", image],
            check=True,
            stderr=log,
        )


def extract_system(image, target):
    reset(target)
    # FAT12 image holding av-cam.bin, vmlinux.bin, initrd.img, ...
    subprocess.run(
        ["7z", "x", "-y", f"-o{target}", image],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def verify(out_dir):
    manifest = Path(__file__).resolve().parent.parent / "manifests" / "sha256.txt"
    if not manifest.exists():
        print("verify: manifest not found, skipped")
        return
    failed = 0
    for line in manifest.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, rel = line.partition("  ")
        path = os.path.join(out_dir, rel.strip())
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        except OSError:
            print(f"verify: MISSING {rel}")
            failed += 1
            continue
        if h.hexdigest() != digest:
            print(f"verify: MISMATCH {rel}")
            failed += 1
    if failed:
        sys.exit(f"verification failed: {failed} file(s)")
    print("verify: ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("updater", help="official Update_ILCE6600V110.exe")
    ap.add_argument("out", help="output directory")
    args = ap.parse_args()

    if not os.path.isfile(args.updater):
        sys.exit(f"not found: {args.updater}")

    check_deps()
    os.makedirs(args.out, exist_ok=True)

    decrypt(args.updater, args.out)
    fw_dir = untar(args.out)

    dev = os.path.join(fw_dir, "0700_part_image", "dev")
    extract_ext2(os.path.join(dev, "nflasha7"), os.path.join(args.out, "rootfs"),
                 os.path.join(args.out, "debugfs-rootfs.log"))
    extract_ext2(os.path.join(dev, "nflasha15"), os.path.join(args.out, "usr"),
                 os.path.join(args.out, "debugfs-usr.log"))
    extract_system(os.path.join(dev, "nflasha3"), os.path.join(args.out, "system"))

    verify(args.out)
    print(f"done: {args.out}")


if __name__ == "__main__":
    main()
