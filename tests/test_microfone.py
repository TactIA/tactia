"""Testes do simulador da cadeia de captação do relógio (ml/tactia_mic.py)."""

import os

import numpy as np
import pytest
import tactia_mic as M

PERFIL = os.path.join(os.path.dirname(__file__), "..", "ml", "perfil_mic_relogio.json")


@pytest.fixture
def mic():
    return M.WatchMic(M.load_profile(PERFIL))


def test_saida_int16_mesmo_tamanho(mic):
    rng = np.random.default_rng(0)
    q, params = mic(np.zeros(16000), rng)
    assert q.dtype == np.int16
    assert len(q) == 16000
    assert 18 <= params["pga_db"] <= 36


def test_piso_de_ruido_bate_com_o_relogio(mic):
    """Em silêncio, o relógio real mede ~ -69 dBFS; o simulado deve ficar perto disso."""
    rng = np.random.default_rng(1)
    niveis = []
    for _ in range(30):
        q, _ = mic(np.zeros(3 * 16000), rng)
        x = q[8000:].astype(float) / 32768
        niveis.append(20 * np.log10(x.std()))
    assert -74 < np.median(niveis) < -64


def test_som_alto_satura_e_som_baixo_nao(mic):
    rng = np.random.default_rng(2)
    t = np.arange(16000) / 16000
    tom = np.sin(2 * np.pi * 1000 * t)
    alto, _ = mic(tom / M.rms(tom) * M.spl_to_pa(125), rng)
    baixo, _ = mic(tom / M.rms(tom) * M.spl_to_pa(60), rng)
    assert np.abs(alto).max() >= 32000
    assert np.abs(baixo).max() < 16000


def test_nivel_cresce_com_o_spl(mic):
    rng = np.random.default_rng(3)
    t = np.arange(16000) / 16000
    tom = np.sin(2 * np.pi * 1000 * t)
    m = mic.sample(rng)
    a, _ = mic(tom / M.rms(tom) * M.spl_to_pa(70), rng, dict(m))
    b, _ = mic(tom / M.rms(tom) * M.spl_to_pa(80), rng, dict(m))
    diferenca = 20 * np.log10(M.rms(b[4000:].astype(float)) / M.rms(a[4000:].astype(float)))
    assert 8.5 < diferenca < 11.5


def test_atraso_fracionario_preserva_energia():
    rng = np.random.default_rng(4)
    x = rng.standard_normal(4096)
    y = M.frac_delay(x, 0.37)
    assert abs(M.rms(y) / M.rms(x) - 1) < 0.02
