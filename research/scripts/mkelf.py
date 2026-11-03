import os, sys, struct
src = sys.argv[1] if len(sys.argv) > 1 else 'out/system/av-cam.bin'
dst = sys.argv[2] if len(sys.argv) > 2 else 'out/avcam.elf'
VA = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
d=open(src,'rb').read()
size=len(d)
shstr=b'\0.text\0.shstrtab\0'
ehsize=52; phentsize=32; phnum=1; shentsize=40; shnum=3
phoff=ehsize; shoff=phoff+phentsize*phnum
# layout: [eh|ph|sh|shstrtab pad] data
strtab_off=shoff+shentsize*shnum
data_off=(strtab_off+len(shstr)+15)&~0xf
out=bytearray(data_off+size)
out[0:16]=b'\x7fELF'+bytes([1,1,1,0])+b'\0'*8
struct.pack_into('<HHIIIIIHHHHHH',out,16,2,40,1,VA,phoff,shoff,0x05000000,ehsize,phentsize,phnum,shentsize,shnum,2)
struct.pack_into('<IIIIIIII',out,phoff,1,data_off,VA,VA,size,size,5,0x1000)
struct.pack_into('<IIIIIIIIII',out,shoff+shentsize,1,1,6,0,data_off,size,0,0,4,0)
struct.pack_into('<IIIIIIIIII',out,shoff+2*shentsize,7,3,0,0,strtab_off,len(shstr),0,0,1,0)
out[strtab_off:strtab_off+len(shstr)]=shstr
out[data_off:data_off+size]=d
os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
open(dst,'wb').write(bytes(out))
print('ok',dst,hex(len(out)))
