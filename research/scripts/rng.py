import sys,re
lo=int(sys.argv[1],16); hi=int(sys.argv[2],16)
pat=re.compile(r'^\s*([0-9a-f]+):')
for line in open('open_gate/avcam.dis'):
    m=pat.match(line)
    if not m: continue
    a=int(m.group(1),16)
    if a<lo: continue
    if a>=hi: break
    print(line.rstrip())
