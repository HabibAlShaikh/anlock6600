import sys, struct
src = sys.argv[1] if len(sys.argv) > 1 else 'out/system/av-cam.bin'
d=open(src,'rb').read()
n=len(d)
targets={
 'mov_aspect_req':0x9d6fec,
 'mov_size_req':0x9d6f7d,
 'mov_sizeh_req':0x9d7027,
 'movrec_mode_req':0x9da78d,
 'e_set_img_frame_size':0x9db499,
 'fmt_1440x1080':0x905396,
 'fmt_table':0x9050e5,
 'paramcheckerr':0x9694e2,
 'v_destsize':0x969390,
 'h_destsize':0x969352,
}
# candidate self-relative encodings: value + position == target (+delta 0..64)
hits={k:[] for k in targets}
for o in range(0,n-4,4):
    w=int.from_bytes(d[o:o+4],'little')
    if w>0x00ffff00: continue
    for k,t in targets.items():
        base=w+o
        if t-64<=base<=t+64:
            hits[k].append((o,w,t-base))
for k,v in hits.items():
    print(k,hex(targets[k]),len(v),[ (hex(o),hex(w),delta) for o,w,delta in v[:12]])
