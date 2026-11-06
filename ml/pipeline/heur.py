import numpy as np, soundfile as sf, scipy.signal as sps
SR=16000
def frame_feats(x, nfft=1024, hop=160):
    f,t,Z=sps.stft(x,fs=SR,nperseg=nfft,noverlap=nfft-hop,boundary=None,padded=False)
    P=np.abs(Z)**2
    band=(f>=300)&(f<=7000)
    Pb=P[band]+1e-12
    tot=Pb.sum(0)
    k=8
    top=np.sort(Pb,axis=0)[-k:].sum(0)
    peak=top/tot
    e_db=10*np.log10(P.sum(0)+1e-12)
    zero=(np.abs(Z).sum(0)<1e-6)
    return t, e_db, peak, zero
def window_scores(x, win=1.0, hop=0.1):
    t,e,pk,zero=frame_feats(x)
    fps=SR/160; W=int(win*fps); H=int(hop*fps)
    starts=[];E=[];T=[];Z=[]
    for s in range(0,max(1,len(e)-W+1),H):
        ee=e[s:s+W]; pp=pk[s:s+W]
        E.append(10*np.log10(np.mean(10**(ee/10))))
        thr=np.median(ee)
        sel=ee>=thr
        T.append(float(np.mean(pp[sel])) if sel.any() else 0.0)
        Z.append(float(np.mean(zero[s:s+W])))
        starts.append(s/fps)
    return np.array(starts),np.array(E),np.array(T),np.array(Z)
