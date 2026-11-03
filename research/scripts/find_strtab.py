import struct,re,collections
d=open('a6600_system/av-cam.bin','rb').read(); n=len(d)
strs=[]
for m in re.finditer(rb'FW: LiroSeq ParamCheckErr@%s\[([a-z0-9_]+)\]', d):
    strs.append((m.start(), m.group(1).decode()))
print('paramcheckerr-style strings',len(strs))
for s,name in strs[:60]: print(' ',hex(s),name)
# build value sets
u32s=set(); u16s=set()
for o in range(0,n-4,2):
    u16s.add(int.from_bytes(d[o:o+2],'little'))
for o in range(0,n-4,4):
    u32s.add(int.from_bytes(d[o:o+4],'little'))
print('u32 set',len(u32s),'u16 set',len(u16s))
s1=strs[0][0]; s2=strs[1][0]; s3=strs[-1][0]
cands=collections.Counter()
for v in u32s:
    if v<0x100be54:
        X=s1-v
        if (s2-X) in u32s and (s3-X) in u32s:
            cands[('u32',X)]+=1
for v in u16s:
    X=s1-v
    if (s2-X) in u16s and (s3-X) in u16s:
        cands[('u16',X)]+=1
print('common-base candidates:',[(k,hex(v)) for k,v in list(cands.items())[:20]])
