import soundfile as sf, numpy as np, scipy.signal as sps, glob, os, sys
from math import gcd
from concurrent.futures import ProcessPoolExecutor
def conv(args):
    src,dst=args
    if os.path.exists(dst): return
    x,fs=sf.read(src,dtype='float32',always_2d=True); x=x.mean(1)
    if fs!=16000:
        g=gcd(16000,fs); x=sps.resample_poly(x,16000//g,fs//g)
    sf.write(dst,np.clip(x,-1,1),16000,subtype='PCM_16')
jobs=[(f,'/home/claude/cache/esc50/'+os.path.basename(f)) for f in glob.glob('/home/claude/src/esc50/audio/*.wav')]
for f in glob.glob('/home/claude/raw/doorbell/*.wav'):
    if 'ambient' in f: continue
    jobs.append((f,'/home/claude/cache/doorbell/'+os.path.basename(f)))
with ProcessPoolExecutor(2) as ex: list(ex.map(conv,jobs))
# ambient longo do thepycoder -> blocos de 60 s
x,fs=sf.read('/home/claude/raw/doorbell/doorbell_detector__raw_data_ambient.wav',dtype='float32',always_2d=True); x=x.mean(1)
x=sps.resample_poly(x,160,441)
for i in range(0,len(x)-16000*60+1,16000*60):
    sf.write(f'/home/claude/cache/pycoder_amb/amb_{i//(16000*60):03d}.wav',x[i:i+16000*60],16000,subtype='PCM_16')
print('ok',len(jobs))
