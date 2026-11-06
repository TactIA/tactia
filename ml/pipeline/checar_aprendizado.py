"""Checagem rápida: o dataset é aprendível e o teste (fontes nunca vistas) generaliza?
Features parecidas com o bloco MFE do Edge Impulse (40 mel, quadro 20 ms, passo 20 ms, dB com piso)."""

import json
import os
import sys
import numpy as np
import soundfile as sf
import collections
from concurrent.futures import ProcessPoolExecutor
import scipy.signal as sps

out = sys.argv[1] if len(sys.argv) > 1 else None
SR = 16000
CL = ["alarme", "ambiente", "buzina", "campainha", "sirene"]


def melbank(n_mels=40, nfft=512, fmin=0, fmax=8000):
    def hz2mel(f):
        return 2595 * np.log10(1 + f / 700)

    def mel2hz(m):
        return 700 * (10 ** (m / 2595) - 1)

    pts = mel2hz(np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2))
    bins = np.floor((nfft + 1) * pts / SR).astype(int)
    fb = np.zeros((n_mels, nfft // 2 + 1))
    for i in range(n_mels):
        a, b, c = bins[i], bins[i + 1], bins[i + 2]
        fb[i, a:b] = (np.arange(a, b) - a) / max(b - a, 1)
        fb[i, b:c] = (c - np.arange(b, c)) / max(c - b, 1)
    return fb


FB = melbank()


def feat(path):
    x, _ = sf.read(path, dtype="float32")
    f, t, Z = sps.stft(x, fs=SR, nperseg=320, noverlap=0, nfft=512, boundary=None, padded=False)
    m = FB @ (np.abs(Z) ** 2)
    db = 10 * np.log10(m + 1e-12)
    db = np.clip((db + 52 + 90) / (90), 0, None)  # piso fixo (escala absoluta, como o MFE)
    return db.astype(np.float32).ravel()


if __name__ == "__main__":
    metas = [m for m in json.load(open(os.path.join(out, "metadados_completos.json"))) if "arquivo" in m]
    paths = [os.path.join(out, m["arquivo"]) for m in metas]
    with ProcessPoolExecutor(2) as ex:
        X = np.stack(list(ex.map(feat, paths, chunksize=256)))
    y = np.array([CL.index(m["classe"]) for m in metas])
    tr = np.array([m["split"] == "train" for m in metas])
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler

    sc = StandardScaler().fit(X[tr])
    clf = MLPClassifier(
        hidden_layer_sizes=(256, 128),
        alpha=1e-3,
        batch_size=256,
        max_iter=40,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=5,
        random_state=0,
    )
    clf.fit(sc.transform(X[tr]), y[tr])
    te = ~tr
    p = clf.predict(sc.transform(X[te]))
    yt = y[te]
    print(f"acurácia teste (fontes nunca vistas): {np.mean(p == yt) * 100:.1f}%  n={te.sum()}")
    from sklearn.metrics import confusion_matrix

    cm = confusion_matrix(yt, p, labels=range(5))
    print("matriz de confusão (linhas=verdade):", CL)
    for c, row in zip(CL, cm):
        print(f"{c:10s}", row, f"{100 * row[CL.index(c)] / row.sum():.1f}%")
    mt = [m for m in metas if m["split"] == "test"]
    grp = collections.defaultdict(list)
    for m, pp in zip(mt, p):
        grp[(m["classe"], m["origem"])].append(CL[pp] == m["classe"])
    for k in sorted(grp):
        print("  ", k, f"{100 * np.mean(grp[k]):.1f}%  n={len(grp[k])}")
