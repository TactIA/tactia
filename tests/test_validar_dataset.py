"""Testes do validador de dataset usado no CI (ml/validar_dataset.py)."""

import json
import os

import numpy as np
import soundfile as sf
from validar_dataset import validar


def _wav(pasta, nome, taxa=16000, segundos=1.0):
    caminho = os.path.join(pasta, nome)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    sf.write(caminho, np.zeros(int(taxa * segundos), dtype=np.int16), taxa, subtype="PCM_16")
    return nome


def _info(pasta, entradas):
    files = [
        {"path": p, "category": c, "label": {"type": "label", "label": r}, "metadata": {"gravacao": g}}
        for p, c, r, g in entradas
    ]
    json.dump({"version": 1, "files": files}, open(os.path.join(pasta, "info.labels"), "w"))


def test_dataset_correto_passa(tmp_path):
    d = str(tmp_path)
    a = _wav(d, "treino/buzina.a.wav")
    b = _wav(d, "teste/buzina.b.wav")
    _info(d, [(a, "training", "buzina", "g1"), (b, "testing", "buzina", "g2")])
    erros, _, resumo = validar(d)
    assert erros == []
    assert resumo["total"] == 2


def test_detecta_vazamento_entre_treino_e_teste(tmp_path):
    d = str(tmp_path)
    a = _wav(d, "treino/sirene.a.wav")
    b = _wav(d, "teste/sirene.b.wav")
    _info(d, [(a, "training", "sirene", "mesma"), (b, "testing", "sirene", "mesma")])
    erros, _, _ = validar(d)
    assert any("vazamento" in e for e in erros)


def test_detecta_formato_e_rotulo_errados(tmp_path):
    d = str(tmp_path)
    a = _wav(d, "treino/alarme.a.wav", taxa=44100)
    b = _wav(d, "treino/campainha.b.wav")
    _info(d, [(a, "training", "alarme", "g1"), (b, "training", "alarme", "g2")])
    erros, _, _ = validar(d)
    assert any("formato" in e for e in erros)
    assert any("não começa com o rótulo" in e for e in erros)


def test_detecta_wav_fora_do_info_labels(tmp_path):
    d = str(tmp_path)
    a = _wav(d, "treino/ambiente.a.wav")
    _wav(d, "treino/ambiente.esquecido.wav")
    _info(d, [(a, "training", "ambiente", "g1")])
    erros, _, _ = validar(d)
    assert any("fora do info.labels" in e for e in erros)
