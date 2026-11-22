/* og.c - LD_PRELOAD shim: 1920x1280 (3:2) in the 1080p24 movie slot.
 *
 * Two changes, in this order:
 *   1. im.elf loads liro.ko via syscall(0x80, image, size,
 *      "fn=/system/av-cam.bin load=1 ..."). Interpose syscall() and rewrite the
 *      fn= path to a verified patched copy. liro.ko checks only ORIL + version,
 *      so the copy loads like the stock image.
 *   2. Only after init_module succeeds, patch the encoder height in libmpr.so:
 *      0x87fe08: 4f f4 87 63 (1080) -> 4f f4 a0 63 (1280).
 *
 * If no verified copy exists, nothing is redirected and libmpr is left stock:
 * a half-applied patch (encoder 1280, record 1080) is the unsafe case. A reboot
 * restores stock behaviour.
 *
 * The copy must already exist; this shim does not write 16 MB at boot.
 * Not loadable on the host: build for armv7 (see build_og.sh).
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#define OLD_PATH "fn=/system/av-cam.bin"
#define AV_SIZE 16825940UL
#define RECORD 0x879C54UL

#define GETPICSIZE "_ZN10MprLibCore14GetPictureSizeEN3MPR11VResolutionEPtS2_"
#define INSN_OFF 0x34 /* 0x87fe08 - 0x87fdd4: start of the mov.w */
#define PATCH_IDX 2   /* 0x87fe0a - 0x87fe08: the 0x87 immediate byte */

/* shortcut: the 0x438 immediate is shared with code 1 (1440x1080), which also
 * becomes 1440x1280. A code-2-only patch needs a code cave; do it later. */
static const unsigned char expect[4] = {0x4f, 0xf4, 0x87, 0x63};

static long (*real_syscall)(long, ...);
static int encoder_patched;

static const char *const candidates[] = {
    "/setting/og-av.bin", /* persistent, 20 MiB partition: tight */
    "/log/og-av.bin",     /* 500 MiB partition */
    "/mnt/og-av.bin",     /* SD card, if mounted here */
};

static int verified_copy(const char *path)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0)
        return 0;

    struct stat st;
    unsigned char h[12], r[0x54];
    int ok = fstat(fd, &st) == 0 && (unsigned long)st.st_size == AV_SIZE &&
             pread(fd, h, sizeof h, 0) == (ssize_t)sizeof h &&
             pread(fd, r, sizeof r, RECORD) == (ssize_t)sizeof r &&
             memcmp(h + 4, "ORIL", 4) == 0 && h[8] == 4 &&
             r[0] == 6 &&                    /* class */
             r[0x0c] == 3 &&                 /* 24p key */
             memcmp(r + 4, "\x80\x07\x00\x05", 4) == 0 &&
             memcmp(r + 0x48, "\x80\x07\x00\x05", 4) == 0 &&
             r[0x34] == 0x08 && r[0x35] == 0x05; /* 1288 */
    close(fd);
    return ok;
}

static const char *pick_copy(void)
{
    for (unsigned i = 0; i < sizeof candidates / sizeof *candidates; i++)
        if (verified_copy(candidates[i]))
            return candidates[i];
    return 0;
}

static void patch_encoder(void)
{
    /* libmpr is already mapped as a startup dependency of im.elf. Look it up in
     * the global scope first: dlopen() by path would map a second copy and the
     * patch would land on a library nobody calls. */
    unsigned char *sym = (unsigned char *)dlsym(RTLD_DEFAULT, GETPICSIZE);
    if (!sym) {
        void *h = dlopen("libmpr.so", RTLD_LAZY | RTLD_GLOBAL);
        if (!h)
            return;
        sym = (unsigned char *)dlsym(h, GETPICSIZE);
        if (!sym)
            return;
    }

    unsigned char *insn = (unsigned char *)((unsigned long)sym & ~1UL) + INSN_OFF;

    for (int i = 0; i < 4; i++)
        if (insn[i] != expect[i])
            return; /* different firmware build: do nothing */

    long page = sysconf(_SC_PAGESIZE);
    unsigned long base = (unsigned long)insn & ~((unsigned long)page - 1);
    if (mprotect((void *)base, (size_t)page, PROT_READ | PROT_WRITE | PROT_EXEC))
        return;

    insn[PATCH_IDX] = 0xa0;
    __builtin___clear_cache((char *)insn, (char *)insn + 4);

    mprotect((void *)base, (size_t)page, PROT_READ | PROT_EXEC);
    encoder_patched = 1;
}

/* Variadic like libc, and must forward all six argument registers: this
 * replaces syscall() for the whole process, so a four-to-six argument call
 * (openat, mmap2, futex) would otherwise lose its extra arguments. Reading
 * past what a shorter call passed yields garbage in unused registers, which
 * the kernel ignores. */
long syscall(long n, ...)
{
    va_list ap;
    long a, b, c, d, e, f;
    va_start(ap, n);
    a = va_arg(ap, long);
    b = va_arg(ap, long);
    c = va_arg(ap, long);
    d = va_arg(ap, long);
    e = va_arg(ap, long);
    f = va_arg(ap, long);
    va_end(ap);

    int redirected = 0;
    if (n == 128 && c) {
        char *params = (char *)c;
        const char *path = pick_copy();
        if (path && strlen(path) <= sizeof OLD_PATH - 4 && /* never grow the string */
            strncmp(params, OLD_PATH, sizeof OLD_PATH - 1) == 0 &&
            strncmp(params + sizeof OLD_PATH - 1, " load=", 6) == 0) {
            char *suffix = params + sizeof OLD_PATH - 1;
            size_t pathlen = strlen(path);
            memmove(params + 3 + pathlen, suffix, strlen(suffix) + 1);
            memcpy(params, "fn=", 3);
            memcpy(params + 3, path, pathlen);
            redirected = 1;
        }
    }

    if (!real_syscall)
        real_syscall = (long (*)(long, ...))dlsym(RTLD_NEXT, "syscall");
    if (!real_syscall)
        return -1;

    long ret = real_syscall(n, a, b, c, d, e, f);
    if (redirected && ret == 0 && !encoder_patched)
        patch_encoder();
    return ret;
}

__attribute__((constructor)) static void og_init(void)
{
    if (!real_syscall)
        real_syscall = (long (*)(long, ...))dlsym(RTLD_NEXT, "syscall");
}
