/* og.c - LD_PRELOAD shim: 1920x1280 (3:2) in the 1080p24 movie slot.
 *
 * Two interposed calls:
 *   1. im.elf loads liro.ko via syscall(0x80, image, size,
 *      "fn=/system/av-cam.bin load=1 ..."). Rewrite the fn= path to a
 *      verified patched copy. liro.ko checks only ORIL + version 4, so the
 *      copy loads like the stock image.
 *   2. libmpr.so is NOT a startup dependency of im.elf: nothing lists it in
 *      DT_NEEDED, im.elf dlopen()s it later through libIMDB.so's module
 *      table (possibly transitively, e.g. via libObj.so, which NEEDs it).
 *      Hook dlopen(), remember the first handle whose scope defines
 *      GetPictureSize, and patch the encoder height only after the fn=
 *      redirect succeeded:
 *      0x87fe08: 4f f4 87 63 (1080) -> 4f f4 a0 63 (1280).
 *
 * If no verified copy exists, nothing is redirected and libmpr is left stock:
 * a half-applied patch (encoder 1280, record 1080) is the unsafe case. The
 * shim never dlopen()s anything itself, so it cannot change the camera's
 * load order. A reboot restores stock behaviour.
 *
 * The copy must already exist; this shim does not write 16 MB at boot.
 * Not loadable on the host: build for armv7 (see build_og.sh). A host build
 * with -DOG_TEST checks the fn= rewrite only.
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
#define MAX_PATH 32 /* im.elf's params buffer is 0x400 bytes (memset 0xb32e) */
#define AV_SIZE 16825940UL
#define RECORD 0x879C54UL

#define GETPICSIZE "_ZN10MprLibCore14GetPictureSizeEN3MPR11VResolutionEPtS2_"
#define INSN_OFF 0x34 /* 0x87fe08 - 0x87fdd4: start of the mov.w */
#define PATCH_IDX 2   /* 0x87fe0a - 0x87fe08: the 0x87 immediate byte */

/* shortcut: the 0x438 immediate is shared with code 1 (1440x1080), which also
 * becomes 1440x1280. A code-2-only patch needs a code cave; do it later. */
static const unsigned char expect[4] = {0x4f, 0xf4, 0x87, 0x63};

static long (*real_syscall)(long, ...);
static void *(*real_dlopen)(const char *, int);
static void *mpr_handle;   /* first loaded object defining GetPictureSize */
static int redirected;     /* liro was pointed at the patched copy */
static int encoder_patched;

static const char *const candidates[] = {
    "/log/og-av.bin", /* 500 MiB, mounted by init before im.elf starts */
    "/mnt/og-av.bin", /* SD card: only if im.elf has mounted it by then */
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

/* Rewrite "fn=/system/av-cam.bin <tail>" in place to "fn=<path> <tail>".
 * Touches nothing unless params is exactly that string and the path fits. */
static int redirect_params(char *params, const char *path)
{
    if (strncmp(params, OLD_PATH, sizeof OLD_PATH - 1) != 0 ||
        strncmp(params + sizeof OLD_PATH - 1, " load=", 6) != 0)
        return 0;
    size_t pathlen = strlen(path);
    if (pathlen > MAX_PATH)
        return 0;
    char *suffix = params + sizeof OLD_PATH - 1;
    memmove(params + 3 + pathlen, suffix, strlen(suffix) + 1);
    memcpy(params, "fn=", 3);
    memcpy(params + 3, path, pathlen);
    return 1;
}

/* Both halves must agree before the encoder changes: the record comes from
 * the redirected copy, so patch only after that load succeeded. */
static void maybe_patch_encoder(void)
{
    if (!redirected || encoder_patched || !mpr_handle)
        return;

    unsigned char *sym = (unsigned char *)dlsym(mpr_handle, GETPICSIZE);
    if (!sym)
        return;
    unsigned char *insn = (unsigned char *)((unsigned long)sym & ~1UL) + INSN_OFF;

    for (int i = 0; i < 4; i++)
        if (insn[i] != expect[i])
            return; /* different firmware build: do nothing */

    long page = sysconf(_SC_PAGESIZE);
    unsigned long base = (unsigned long)insn & ~((unsigned long)page - 1);
    size_t len = (size_t)page;
    if (base + (unsigned long)page <= (unsigned long)insn + 4) /* straddles */
        len += (size_t)page;

    if (mprotect((void *)base, len, PROT_READ | PROT_WRITE | PROT_EXEC))
        return;

    insn[PATCH_IDX] = 0xa0;
    __builtin___clear_cache((char *)insn, (char *)insn + 4);

    mprotect((void *)base, len, PROT_READ | PROT_EXEC);
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

    int rewrote = 0;
    if (n == 128 && c) {
        const char *path = pick_copy();
        if (path)
            rewrote = redirect_params((char *)c, path);
    }

    if (!real_syscall)
        real_syscall = (long (*)(long, ...))dlsym(RTLD_NEXT, "syscall");
    if (!real_syscall)
        return -1;

    long ret = real_syscall(n, a, b, c, d, e, f);
    if (rewrote && ret == 0)
        redirected = 1;
    maybe_patch_encoder();
    return ret;
}

/* im.elf dlopen()s libmpr.so itself (via libIMDB.so's table), possibly as a
 * dependency of another dlopen; either way dlsym(handle) reaches it. */
void *dlopen(const char *file, int flags)
{
    if (!real_dlopen)
        real_dlopen = (void *(*)(const char *, int))dlsym(RTLD_NEXT, "dlopen");
    void *h = real_dlopen ? real_dlopen(file, flags) : 0;
    if (h && !mpr_handle && dlsym(h, GETPICSIZE))
        mpr_handle = h;
    maybe_patch_encoder();
    return h;
}

#ifdef OG_TEST
/* Host self-check for the fn= rewrite, the only arch-independent logic. */
#include <assert.h>
#include <stdio.h>

#define ORIG "fn=/system/av-cam.bin load=1 debug=1 adr=0x12345678 delay=1"

int main(void)
{
    char buf[0x400];
    char path[MAX_PATH + 8];

    strcpy(buf, ORIG);
    assert(redirect_params(buf, "/log/og-av.bin"));
    assert(!strcmp(buf, "fn=/log/og-av.bin load=1 debug=1 adr=0x12345678 delay=1"));

    strcpy(buf, ORIG);
    assert(redirect_params(buf, "/mnt/og-av.bin"));
    assert(!strcmp(buf, "fn=/mnt/og-av.bin load=1 debug=1 adr=0x12345678 delay=1"));

    /* the rewrite may grow the string; the 0x400 buffer has ~64 used */
    memset(path, 'x', sizeof path);
    memcpy(path, "/log/", 5);
    path[MAX_PATH] = '\0';
    strcpy(buf, ORIG);
    assert(redirect_params(buf, path));
    assert(!strncmp(buf, "fn=/log/", 8));
    assert(strstr(buf, " load=1 debug=1 adr=0x12345678 delay=1"));

    path[MAX_PATH] = 'x';
    path[MAX_PATH + 1] = '\0';
    strcpy(buf, ORIG);
    assert(!redirect_params(buf, path)); /* one char over the bound */
    assert(!strcmp(buf, ORIG));         /* buffer untouched */

    strcpy(buf, "fn=/other.bin load=1");
    assert(!redirect_params(buf, "/log/og-av.bin"));
    assert(!strcmp(buf, "fn=/other.bin load=1"));

    puts("og: fn= rewrite ok");
    return 0;
}
#endif
