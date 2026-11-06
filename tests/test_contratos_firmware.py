"""Contratos entre o firmware e o script de captura.

Esses valores precisam ser iguais nos dois lados; quando não eram, o dataset saiu
com áudio corrompido (baud diferente) ou com espectro diferente do que o modelo vê
no relógio (ganho diferente entre captura e inferência).
"""

import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..")
CAPTURA = os.path.join(RAIZ, "firmware", "captura", "captura.ino")
INFERENCIA = os.path.join(RAIZ, "firmware", "inferencia", "inferencia.ino")
SCRIPT = os.path.join(RAIZ, "tools", "captura_audio.py")


def _ler(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _um(padrao, texto):
    achados = set(re.findall(padrao, texto))
    assert len(achados) == 1, f"esperava um valor para {padrao!r}, achei {achados}"
    return achados.pop()


def test_baud_rate_da_captura_igual_ao_script():
    sketch = _um(r"Serial\.begin\((\d+)\)", _ler(CAPTURA))
    script = re.search(r"^BAUD_RATE\s*=\s*(\d+)", _ler(SCRIPT), re.M).group(1)
    assert sketch == script


def test_taxa_de_amostragem_igual_nos_tres():
    captura = _um(r"#define\s+SAMPLE_RATE\s+(\d+)", _ler(CAPTURA))
    inferencia = _um(r"#define\s+SAMPLE_RATE\s+(\d+)", _ler(INFERENCIA))
    script = re.search(r"^SAMPLE_RATE\s*=\s*(\d+)", _ler(SCRIPT), re.M).group(1)
    assert captura == inferencia == script == "16000"


def test_ganho_do_microfone_igual_na_captura_e_na_inferencia():
    captura = _um(r"uint8_t\s+gainVal\s*=\s*(\d+)", _ler(CAPTURA))
    inferencia = _um(r"uint8_t\s+gainVal\s*=\s*(\d+)", _ler(INFERENCIA))
    assert captura == inferencia
