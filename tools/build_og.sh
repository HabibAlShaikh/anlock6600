#!/bin/sh
# Build the a6600 LD_PRELOAD shim (armv7, EABI5, no libc dependency).
set -eu
cd "$(dirname "$0")"

# Host self-check of the fn= rewrite first: plain string logic, no target
# hardware needed. The two interposed hooks cannot be tested on the host.
t=$(mktemp)
trap 'rm -f "$t"' EXIT
cc -DOG_TEST -O2 -o "$t" og.c
"$t"

clang --target=armv7-linux-gnueabihf -march=armv7-a -mthumb \
      -mfloat-abi=soft -O2 -fPIC -fno-stack-protector -shared -nostdlib -fuse-ld=lld \
      -Wl,-soname,og.so -o og.so og.c

readelf -hW og.so | grep -E 'Class|Machine|Flags'
echo "--- undefined symbols (must all exist in im.elf's libs) ---"
readelf --dyn-syms -W og.so | awk '$7 == "UND" && $8 != "" {print $8}'
readelf --dyn-syms -W og.so | \
  awk '$4 == "FUNC" && $5 == "GLOBAL" && $8 == "syscall" {s = 1}
       $4 == "FUNC" && $5 == "GLOBAL" && $8 == "dlopen" {d = 1}
       END {exit !(s && d)}' \
  || { echo "og.so must export syscall and dlopen" >&2; exit 1; }
