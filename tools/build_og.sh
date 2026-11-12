#!/bin/sh
# Build the a6600 LD_PRELOAD shim (armv7, EABI5, no libc dependency).
set -eu
cd "$(dirname "$0")"
clang --target=armv7-linux-gnueabihf -march=armv7-a -mthumb \
      -mfloat-abi=soft -O2 -fPIC -shared -nostdlib -fuse-ld=lld \
      -Wl,-soname,og.so -o og.so og.c

readelf -hW og.so | grep -E 'Class|Machine|Flags'
echo "--- undefined symbols (must all exist in im.elf's libs) ---"
readelf --dyn-syms -W og.so | awk '$7 == "UND" && $8 != "" {print $8}'
echo "--- constructors ---"
readelf -x .init_array og.so 2>/dev/null | tail -1
