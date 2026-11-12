/* og.c - LD_PRELOAD shim: make the 1080p encoder size 1920x1280 (3:2).
 *
 * MprLibCore::GetPictureSize() is a static function with a 13-entry TBB and no
 * caller outside libmpr.so, so symbol interposition cannot reach it. Instead
 * this library finds the already-loaded libmpr, checks the exact instruction it
 * expects, and rewrites the height immediate of the 1920x1080 case in memory.
 *
 *   0x87fe08: 4f f4 87 63   mov.w r3, #0x438   (1080)
 *   0x87fe0a: 0x87 -> 0xa0  mov.w r3, #0x500   (1280)
 *
 * Nothing on disk changes; a reboot restores stock behaviour. Any mismatch
 * leaves the camera untouched.
 *
 * Not loadable on the host: build for armv7 (see build_og.sh).
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/mman.h>
#include <unistd.h>

#define GETPICSIZE "_ZN10MprLibCore14GetPictureSizeEN3MPR11VResolutionEPtS2_"
#define INSN_OFF 0x34 /* 0x87fe08 - 0x87fdd4: start of the mov.w */
#define PATCH_IDX 2   /* 0x87fe0a - 0x87fe08: the 0x87 immediate byte */

/* shortcut: the 0x438 immediate is shared with code 1 (1440x1080), which also
 * becomes 1440x1280. A code-2-only patch needs a code cave; do it later. */
static const unsigned char expect[4] = {0x4f, 0xf4, 0x87, 0x63};

__attribute__((constructor)) static void og_init(void)
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
}
