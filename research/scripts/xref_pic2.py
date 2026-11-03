import json, collections
d=open('a6600_system/av-cam.bin','rb').read(); n=len(d)
def u32(o): return int.from_bytes(d[o:o+4],'little')
def u16(o): return int.from_bytes(d[o:o+2],'little')
def addpc(rt): return 0x4400|(0xF<<3)|rt
refs=collections.defaultdict(list)
i=0
while i<n-8:
    h=u16(i); rt=None; pool=None; nxt=2
    if 0x4800<=h<=0x4FFF:
        rt=(h>>8)&7; pool=((i+4)&~3)+(h&0xff)*4
    elif h==0xF8DF and i+4<=n:
        h2=u16(i+2); rt=(h2>>12)&0xF; pool=((i+4)&~3)+(h2&0xFFF); nxt=4
    if rt is not None and rt!=15 and pool is not None and pool+4<=n:
        for k in range(nxt, nxt+16, 2):
            if i+k+2>n: break
            if u16(i+k)==addpc(rt):
                refs[u32(pool)+i+k+4].append(i); break
    i+=2
print('refs',sum(len(v) for v in refs.values()),'targets',len(refs))
json.dump({str(k):v for k,v in refs.items()},open('open_gate/picrefs2.json','w'))
T={'invalid_record_size':0x9694eb,'invalid_aspect_d':0x9691fc,'invalid_aspect':0x9692e8,
   'h_dest':0x96935c,'dest2':0x96934a,'paramcheckerr':0x9694e2,
   'size_tbl':0x834b14,'fmt_tbl':0x9050e5,'fmt_1440':0x905396}
for k,t in T.items():
    print(k,hex(t),[hex(x) for x in sorted(refs.get(t,[]))][:6])
