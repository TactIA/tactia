"""
Calibra o simulador com gravações reais do relógio.
Usa gravações de SILÊNCIO (sala quieta) para medir:
  - o piso de ruído na saída (dBFS) e o formato do espectro dele (ruído do MEMS + sala + elétrico);
  - o zumbido de baixa frequência (~50-62 Hz) e harmônicos;
  - tons espúrios estreitos (ex.: 6 kHz);
  - a ressonância da porta acústica (lombada larga no espectro do piso).
Saída: perfil_mic.json, lido por tactia_mic.WatchMic.

Uso: python3 calibrar_microfone.py perfil_mic.json silencio1.wav silencio2.wav ...
"""

import sys
import json
import numpy as np
import soundfile as sf
import scipy.signal as sps

out = sys.argv[1]
files = sys.argv[2:]
x = np.concatenate([sf.read(p, dtype="float64")[0] for p in files])
rms_dbfs = 20 * np.log10(x.std())

# PSD em alta resolução para tons; em baixa resolução para o formato do piso
f_hi, P_hi = sps.welch(x, 16000, nperseg=16384)
f, P = sps.welch(x, 16000, nperseg=1024)
db = 10 * np.log10(P + 1e-20)
db_hi = 10 * np.log10(P_hi + 1e-20)

# tons estreitos: picos > 6 dB acima da mediana local (resolução ~1 Hz)
med = sps.medfilt(db_hi, 101)
tons = []
for i in sps.find_peaks(db_hi - med, height=6, distance=20)[0]:
    fc = float(f_hi[i])
    if fc < 20:
        continue
    b, a = sps.iirpeak(fc, 30, fs=16000)
    lvl = 20 * np.log10(sps.lfilter(b, a, x).std() + 1e-12)
    tons.append({"hz": round(fc, 1), "dbfs": round(float(lvl), 1)})
tons = sorted(tons, key=lambda t: -t["dbfs"])[:6]

# piso suave (sem os tons) para gerar ruído com o mesmo espectro
smooth = sps.medfilt(db, 9)
# ressonância: maior lombada entre 3 e 7.5 kHz em relação a uma reta log-log do piso
sel = (f > 300) & (f < 7500)
coef = np.polyfit(np.log10(f[sel]), smooth[sel], 1)
resid = smooth - np.polyval(coef, np.log10(np.maximum(f, 1)))
band = (f > 3000) & (f < 7500)
ir = np.argmax(resid[band])
res_hz = float(f[band][ir])
res_db = float(resid[band][ir])

perfil = {
    "fonte_calibracao": f"{len(files)} gravações de silêncio do relógio ({len(x) / 16000:.0f} s)",
    "floor_rms_dbfs": round(float(rms_dbfs), 2),
    "floor_psd_hz": [round(float(v), 1) for v in f],
    "floor_psd_db": [round(float(v), 2) for v in smooth],
    "tons": tons,
    "inclinacao_db_por_decada": round(float(coef[0]), 1),
    "res_hz": [max(3000.0, res_hz - 400), min(7600.0, res_hz + 400)],
    "res_gain_db": [max(1.0, res_db - 2), res_db + 2],
}
json.dump(perfil, open(out, "w"), indent=1, ensure_ascii=False)
print(json.dumps({k: v for k, v in perfil.items() if not k.startswith("floor_psd")}, indent=1, ensure_ascii=False))
