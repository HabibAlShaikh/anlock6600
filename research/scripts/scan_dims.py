#!/usr/bin/env python3
"""Scan binaries for adjacent width/height constants (u16le, u32le, ascii)."""
import os, re, struct, sys

PAIRS = [(1920,1080),(1280,720),(3840,2160),(1920,1280),(1920,1440),(2880,1920),
         (4240,2832),(6000,4000),(6000,3376),(6016,4016),(4096,2160),(2048,1080),
         (1440,1080),(640,480),(640,360),(480,270),(800,480),(2120,1416),(3008,2008),
         (4240,2400),(1920,804),(1920,817),(1920,824)]
ROOTS = sys.argv[1:]

def scan(path):
    try:
        if os.path.getsize(path) > 40*1024*1024: return []
        d = open(path,'rb').read()
    except Exception:
        return []
    out=[]
    for (w,h) in PAIRS:
        pats = {
          'u16': struct.pack('<HH', w, h),
          'u32': struct.pack('<II', w, h),
        }
        for kind, pat in pats.items():
            start=0
            while True:
                i=d.find(pat,start)
                if i<0: break
                out.append((path,i,kind,w,h))
                start=i+1
                if len(out)>4000: return out
    return out

for root in ROOTS:
    for dirpath,_,files in os.walk(root):
        for f in files:
            p=os.path.join(dirpath,f)
            for r in scan(p):
                print("%s\t0x%x\t%s\t%dx%d" % r)
