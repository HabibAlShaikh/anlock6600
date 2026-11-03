import struct
src='a6600_system/av-cam.bin'
d=open(src,'rb').read()
VA=0; size=len(d)
shstr=b'\0.text\0.shstrtab\0'
ehsize=52; phentsize=32; phnum=1; shentsize=40; shnum=3
phoff=ehsize; shoff=phoff+phentsize*phnum
data_off=(shoff+shentsize*shnum+len(shstr)+0xfff)&~0xfff
str_off=data_off-size and 0
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
open('open_gate/avcam.elf','wb').write(bytes(out))
print('ok',hex(len(out)))
