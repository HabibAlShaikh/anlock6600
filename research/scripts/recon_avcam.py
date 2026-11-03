import struct, collections
d=open('a6600_system/av-cam.bin','rb').read()
n=len(d)
print('size',hex(n),n)
print('head',d[:64].hex())
print('tail',d[-32:].hex())
# high word stats
hi=collections.Counter()
for o in range(0,n-4,4):
    v=int.from_bytes(d[o:o+4],'little')
    if v>=0x01000000:
        hi[v>>24]+=1
print('high byte histogram',sorted(hi.items()))
# top exact values
tops=collections.Counter()
for o in range(0,n-4,4):
    v=int.from_bytes(d[o:o+4],'little')
    if 0x10000000<=v<0xF0000000:
        tops[v]+=1
print('distinct high words',len(tops))
print('top20',[(hex(k),c) for k,c in tops.most_common(20)])
