"""Treina o MLP de referência num dataset gerado e testa nas gravações REAIS do relógio (dataset_limpo, sem 'sim')."""

from config import DATASET_RELOGIO, WORK
import json
import os
import sys
import numpy as np
import collections
import soundfile as sf
from concurrent.futures import ProcessPoolExecutor
from checar_aprendizado import feat, CL, FB
import scipy.signal as sps
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

gen = sys.argv[1]
tag = sys.argv[2]
U = os.path.dirname(DATASET_RELOGIO.rstrip("/")) + "/"  # pasta datasets/ (info.labels único)


def feat_arr(x):
    f, t, Z = sps.stft(x, fs=16000, nperseg=320, noverlap=0, nfft=512, boundary=None, padded=False)
    db = 10 * np.log10(FB @ (np.abs(Z) ** 2) + 1e-12)
    return np.clip((db + 142) / 90, 0, None).astype(np.float32).ravel()


def real_windows(fo):
    x, _ = sf.read(U + fo["path"], dtype="float32")
    if len(x) < 16000:
        x = np.pad(x, (0, 16000 - len(x)))
    out = []
    for s in range(0, len(x) - 16000 + 1, 8000):
        out.append(feat_arr(x[s : s + 16000]))
    return out


metas = [m for m in json.load(open(os.path.join(gen, "metadados_completos.json"))) if "arquivo" in m]
cache = f"{WORK}feats_{tag}.npy"
if os.path.exists(cache):
    X = np.load(cache)
else:
    with ProcessPoolExecutor(2) as ex:
        X = np.stack(list(ex.map(feat, [os.path.join(gen, m["arquivo"]) for m in metas], chunksize=256)))
    np.save(cache, X)
y = np.array([CL.index(m["classe"]) for m in metas])
fl = [f for f in json.load(open(U + "info.labels"))["files"] if f["metadata"].get("origem") == "relogio"]
with ProcessPoolExecutor(2) as ex:
    RW = list(ex.map(real_windows, fl))
Xr = []
yr = []
sr = []
rid = []
for i, (fo, ws) in enumerate(zip(fl, RW)):
    for w in ws:
        Xr.append(w)
        yr.append(CL.index(fo["label"]["label"]))
        sr.append(fo["metadata"]["sessao"])
        rid.append(i)
Xr = np.stack(Xr)
yr = np.array(yr)
sr = np.array(sr)
rid = np.array(rid)
accs = []
for seed in [0, 1]:
    sc = StandardScaler().fit(X)
    clf = MLPClassifier(
        hidden_layer_sizes=(256, 128),
        alpha=1e-3,
        batch_size=256,
        max_iter=40,
        early_stopping=True,
        n_iter_no_change=5,
        random_state=seed,
    ).fit(sc.transform(X), y)
    p = clf.predict(sc.transform(Xr))
    accs.append(p)
for seed, p in enumerate(accs):
    print(
        f"[{tag} seed{seed}] acuracia por janela nas gravacoes reais do relogio: {100 * np.mean(p == yr):.1f}%  n={len(yr)}"
    )
p = accs[0]
from sklearn.metrics import confusion_matrix

cm = confusion_matrix(yr, p, labels=range(5))
print(CL)
for c, row in zip(CL, cm):
    print(f"{c:10s}", row, f"{100 * row[CL.index(c)] / max(row.sum(), 1):.1f}%")
res = collections.defaultdict(list)
for a, b, s in zip(p, yr, sr):
    res[(CL[b], s)].append(a == b)
print(" | ".join(f"{c[:4]}-{s}:{100 * np.mean(v):.0f}%" for (c, s), v in sorted(res.items())))
