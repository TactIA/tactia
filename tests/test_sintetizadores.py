"""Testes dos sintetizadores físicos (ml/tactia_synth.py)."""

import numpy as np
import pytest
import scipy.signal as sps
import tactia_synth as S

SINTETIZADORES = [f for tabela in (S.DOORBELL_SYNTHS, S.ALARM_SYNTHS, S.HORN_SYNTHS, S.SIREN_SYNTHS) for f, _ in tabela]
SINTETIZADORES.append(S.watch_vibration_motor)


@pytest.mark.parametrize("fn", SINTETIZADORES, ids=lambda f: f.__name__)
@pytest.mark.parametrize("semente", [0, 1, 2])
def test_saida_valida(fn, semente):
    y, info = fn(np.random.default_rng(semente))
    assert np.all(np.isfinite(y))
    assert len(y) >= 0.5 * S.SR
    assert np.abs(y).max() > 0
    assert isinstance(info.get("tipo"), str)


@pytest.mark.parametrize("fn", SINTETIZADORES, ids=lambda f: f.__name__)
def test_energia_dentro_da_banda_do_relogio(fn):
    """A 16 kHz nada pode passar de 8 kHz; quase toda a energia deve ficar abaixo de 7,5 kHz."""
    y, _ = fn(np.random.default_rng(7))
    f, p = sps.welch(y, S.SR, nperseg=1024)
    assert p[f > 7500].sum() / p.sum() < 0.01


@pytest.mark.parametrize("fn", SINTETIZADORES, ids=lambda f: f.__name__)
def test_reprodutivel_com_a_mesma_semente(fn):
    a, _ = fn(np.random.default_rng(42))
    b, _ = fn(np.random.default_rng(42))
    assert np.array_equal(a, b)
