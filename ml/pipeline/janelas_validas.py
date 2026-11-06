"""Calcula, para cada fonte real, os inícios de janela de 1 s em que o evento está presente."""

from config import WORK
import json
import numpy as np
import soundfile as sf
from concurrent.futures import ProcessPoolExecutor
from heur import window_scores

W = WORK
TAGS = {}
try:
    TAGS = json.load(open(W + "tags.json"))
except Exception:
    pass


def valid_for(it):
    x, fs = sf.read(it["path"], dtype="float32", always_2d=True)
    x = x.mean(1)
    dur = len(x) / 16000
    if dur < 1.0:
        x = np.pad(x, (0, 16000 - len(x)))
    s, E, T, Z = window_scores(x)
    ok = Z < 0.2
    cls = it["cls"]
    if cls == "ambiente":
        ok &= E > -75  # evita trechos praticamente mudos (silêncio digital)
        # se houver etiquetas do tagger, descarta janelas com alerta escondido
        tg = TAGS.get(it["path"])
        if tg:
            t = np.array(tg["t"])
            pmax = np.max(
                [np.array(tg[g]) for g in ["sirene", "buzina", "alarme", "campainha", "outros_alertas"]], axis=0
            )
            bad = t[pmax > 0.2]
            for b in bad:
                ok &= ~((s > b - 1.0) & (s < b + 1.0))
        return [round(float(v), 2) for v in s[ok]], None
    # classes-alvo
    tg = TAGS.get(it["path"])
    if "strong" in it:
        cover = np.zeros_like(s)
        for on, off in it["strong"]:
            cover += np.clip(np.minimum(s + 1, off) - np.maximum(s, on), 0, None)
        ok &= (cover >= 0.4) & (E >= E.max() - 20)
        how = "rotulo_forte"
    elif tg:
        t = np.array(tg["t"])
        p = np.interp(s + 0.5, t + 0.5, np.array(tg[cls]))
        ok &= (p >= 0.3) & (E >= E.max() - 18)
        how = "tagger"
    else:
        if T[E >= E.max() - 12].max() < 0.55:
            return [], "descartado_pouco_tonal"
        ok &= (E >= E.max() - 12) & (T >= 0.6)
        how = "heuristica_tonal"
    return [round(float(v), 2) for v in s[ok]], how


def run(i_it):
    i, it = i_it
    try:
        v, how = valid_for(it)
    except Exception as e:
        v, how = [], "erro:" + str(e)[:60]
    return i, v, how


if __name__ == "__main__":
    inv = json.load(open(W + "inventario.json"))
    with ProcessPoolExecutor(2) as ex:
        for i, v, how in ex.map(run, list(enumerate(inv)), chunksize=32):
            inv[i]["valid"] = v
            inv[i]["metodo"] = how
    json.dump(inv, open(W + "inventario_validas.json", "w"), ensure_ascii=False)
    import collections

    c = collections.Counter()
    w = collections.Counter()
    for it in inv:
        c[(it["cls"], it.get("metodo"), len(it["valid"]) > 0)] += 1
        w[it["cls"]] += len(it["valid"])
    for k, v in sorted(c.items(), key=str):
        print(v, k)
    print(dict(w))
