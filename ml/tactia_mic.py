"""
Simulador da cadeia acústica + microfone do TactIA
(Waveshare ESP32-S3-Touch-AMOLED-1.75: 2 mics MEMS analógicos -> ES7210 -> I2S 16 kHz / 16 bit).

Cadeia aplicada a cada janela (pressão sonora em Pa -> amostras int16):
  fonte seca -> resposta da sala/ambiente externo (RIR) -> nível SPL alvo
  + fundo (outra gravação, com SPL próprio)
  -> efeito de pulso/corpo (sombra acústica)
  -> par de microfones (atraso entre mics + descasamento de sensibilidade)
  -> MEMS: passa-altas (furo de ventilação + acoplamento AC), ressonância da porta acústica,
     saturação suave perto do AOP, ruído próprio (SNR ~57-66 dB(A))
  -> sensibilidade (dBV/Pa) -> PGA do ES7210 (18-36 dB; exemplo da Waveshare usa 24 dB)
  -> ADC: fundo de escala, offset DC, clipping duro, filtro de decimação (~0.4535*Fs),
     passa-altas digital, espúrios elétricos de baixo nível, quantização 16 bit.

Parâmetros que não constam no esquemático (modelo exato do MEMS) são sorteados em faixas
típicas de MEMS analógicos, para o modelo não depender de um valor exato. Se você tiver
gravações reais do relógio, `perfil_mic.json` (gerado por calibrar_microfone.py) estreita
essas faixas para o seu exemplar.
"""
import json
import numpy as np
import scipy.signal as sps

SR = 16000
P_REF = 20e-6


def db2lin(db):
    return 10.0 ** (np.asarray(db) / 20.0)


def spl_to_pa(spl):
    return P_REF * db2lin(spl)


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)) + 1e-20))


# ---------------------------------------------------------------- biquads RBJ
def _biquad(kind, f0, q=0.707, gain_db=0.0):
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * min(f0, SR * 0.49) / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2 * q)
    if kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "lowshelf":
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sa)]
        a = [(A + 1) + (A - 1) * cw + sa, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sa]
    elif kind == "highshelf":
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sa)]
        a = [(A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa]
    else:
        raise ValueError(kind)
    b, a = np.array(b) / a[0], np.array(a) / a[0]
    return b, a


def frac_delay(x, d_samples):
    """Atraso fracionário via fase no domínio da frequência."""
    n = len(x)
    N = 1 << int(np.ceil(np.log2(n + 64)))
    X = np.fft.rfft(x, N)
    k = np.arange(len(X))
    X *= np.exp(-2j * np.pi * k * d_samples / N)
    return np.fft.irfft(X, N)[:n]


# ---------------------------------------------------------------- RIRs
def _diffuse_tail(rng, rt60_bands, length, onset):
    """Cauda difusa com decaimento dependente da frequência (4 bandas)."""
    n = int(length * SR)
    t = np.arange(n) / SR
    edges = [(None, 500), (500, 1500), (1500, 4000), (4000, None)]
    tail = np.zeros(n)
    for (lo, hi), rt in zip(edges, rt60_bands):
        w = rng.standard_normal(n)
        if lo is None:
            sos = sps.butter(4, hi, btype="low", fs=SR, output="sos")
        elif hi is None:
            sos = sps.butter(4, lo, btype="high", fs=SR, output="sos")
        else:
            sos = sps.butter(2, [lo, hi], btype="band", fs=SR, output="sos")
        tail += sps.sosfilt(sos, w) * np.exp(-6.91 * t / rt)
    tail[: int(onset * SR)] *= np.linspace(0, 1, int(onset * SR)) ** 2
    return tail


def make_indoor_rir(rng):
    rt60 = rng.uniform(0.18, 0.95)
    dist = rng.uniform(0.4, 7.0)
    bands = [rt60 * rng.uniform(1.0, 1.3), rt60, rt60 * rng.uniform(0.75, 0.95), rt60 * rng.uniform(0.45, 0.75)]
    length = min(1.2, rt60 * 1.1 + 0.05)
    h = np.zeros(int(length * SR))
    h[0] = 1.0
    # reflexões iniciais
    for _ in range(rng.integers(4, 14)):
        d = rng.uniform(0.002, 0.035)
        idx = int(d * SR)
        if idx < len(h):
            h[idx] += rng.uniform(-0.6, 0.6) / (1 + d * 60)
    tail = _diffuse_tail(rng, bands, length, rng.uniform(0.004, 0.02))
    # razão direto/reverberante cai com a distância
    drr_db = 12 - 20 * np.log10(dist + 0.3) * rng.uniform(0.9, 1.4) + rng.normal(0, 2)
    tail *= np.sqrt(np.sum(h ** 2) / (np.sum(tail ** 2) + 1e-12)) * db2lin(-drr_db)
    h = h + tail
    return h / (np.max(np.abs(h)) + 1e-12), {"amb": "interno", "rt60": round(rt60, 2), "dist_m": round(dist, 1)}


def make_outdoor_rir(rng, dist):
    length = 0.5
    h = np.zeros(int(length * SR))
    h[0] = 1.0
    # reflexão do chão
    dg = rng.uniform(0.0005, 0.006)
    h[int(dg * SR)] += rng.uniform(0.3, 0.8)
    # fachadas/prédios
    for _ in range(rng.integers(0, 5)):
        d = rng.uniform(0.01, 0.35)
        if int(d * SR) < len(h):
            h[int(d * SR)] += rng.uniform(0.03, 0.35) * rng.choice([-1, 1])
    tail = _diffuse_tail(rng, [rng.uniform(0.2, 0.6)] * 2 + [0.15, 0.08], length, 0.01)
    tail *= np.sqrt(np.sum(h ** 2) / (np.sum(tail ** 2) + 1e-12)) * db2lin(-rng.uniform(12, 25))
    h = h + tail
    # absorção do ar (distância)
    fc = float(np.clip(9000 / (1 + dist / 120.0), 2200, 7400))
    sos = sps.butter(2, fc, btype="low", fs=SR, output="sos")
    h = sps.sosfilt(sos, h)
    return h / (np.max(np.abs(h)) + 1e-12), {"amb": "externo", "dist_m": round(float(dist), 1)}


def through_window(rng, x):
    """Som externo ouvido de dentro de casa (janela/parede): atenuação forte dos agudos."""
    fc = rng.uniform(350, 1600)
    sos = sps.butter(2, fc, btype="low", fs=SR, output="sos")
    y = sps.sosfilt(sos, x)
    return 0.7 * y + 0.3 * sps.sosfilt(sps.butter(1, fc * 3, fs=SR, output="sos"), x) * db2lin(-rng.uniform(6, 18))


# ---------------------------------------------------------------- microfone
DEFAULT_PROFILE = {
    "sens_dbv": [-40.0, -36.0],        # sensibilidade MEMS analógico típica (dBV/Pa)
    "pga_db": [18, 21, 24, 24, 24, 24, 27, 27, 30, 33],
    "fs_dbv": [-6.0, 0.0],              # entrada de fundo de escala do ADC (dBV rms)
    "hpf_hz": [60.0, 220.0],
    "res_hz": [3500.0, 7000.0],
    "res_gain_db": [1.0, 8.0],
    "res_q": [0.8, 3.0],
    "lpf_hz": [6600.0, 7400.0],
    "snr_dba": [57.0, 66.0],
    "aop_spl": [116.0, 124.0],
    "p_dual_avg": 0.4,
    "p_spur": 0.25,
    "dc_dbfs": -50.0,
}


def load_profile(path=None):
    prof = dict(DEFAULT_PROFILE)
    if path:
        with open(path) as f:
            prof.update(json.load(f))
    return prof


class WatchMic:
    def __init__(self, profile=None):
        self.p = profile or dict(DEFAULT_PROFILE)
        if "floor_psd_db" in self.p:
            f = np.array(self.p["floor_psd_hz"]); d = np.array(self.p["floor_psd_db"])
            self._ff, self._fd = f, d

    def _floor_noise(self, rng, n, m):
        N = 1 << int(np.ceil(np.log2(n)))
        fr = np.fft.rfftfreq(N, 1 / SR)
        tilt = rng.uniform(-1.5, 1.5) * np.log2(np.maximum(fr, 50) / 1000)  # pequena variação de inclinação
        mag = 10 ** ((np.interp(fr, self._ff, self._fd) + tilt) / 20)
        spec = (rng.standard_normal(len(fr)) + 1j * rng.standard_normal(len(fr))) * mag
        z = np.fft.irfft(spec, N)[:n]
        lvl = self.p["floor_rms_dbfs"] + (m["pga_db"] - 24) + rng.uniform(-3, 3)
        return z / (rms(z) + 1e-20) * db2lin(lvl)

    def sample(self, rng):
        p = self.p
        u = lambda k: float(rng.uniform(*p[k]))
        return {
            "sens_dbv": u("sens_dbv"),
            "pga_db": float(rng.choice(p["pga_db"])),
            "fs_dbv": u("fs_dbv"),
            "hpf_hz": float(np.exp(rng.uniform(np.log(p["hpf_hz"][0]), np.log(p["hpf_hz"][1])))),
            "res_hz": u("res_hz"), "res_gain_db": u("res_gain_db"), "res_q": u("res_q"),
            "lpf_hz": u("lpf_hz"),
            "snr_dba": u("snr_dba"),
            "aop_spl": u("aop_spl"),
            "dual_avg": bool(rng.random() < p["p_dual_avg"]),
            "mic_delay_us": float(rng.uniform(-90, 90)),
            "mic_mismatch_db": float(rng.normal(0, 0.7)),
            "body_low_db": float(rng.uniform(-2, 4)),
            "body_high_db": float(rng.uniform(-8, 2)),
            "spur": bool(rng.random() < p["p_spur"]),
            "dc": float(rng.normal(0, db2lin(p["dc_dbfs"]))),
        }

    def pa_per_fs(self, m):
        """Quantos Pa (pico) levam o ADC a 0 dBFS."""
        v_fs_peak = db2lin(m["fs_dbv"]) * np.sqrt(2)
        return v_fs_peak / (db2lin(m["sens_dbv"]) * db2lin(m["pga_db"]))

    def spl_at_0dbfs(self, m):
        return 20 * np.log10(self.pa_per_fs(m) / np.sqrt(2) / P_REF)

    def __call__(self, pa, rng, m=None):
        """pa: sinal em Pascal (float). Retorna int16 e os parâmetros usados."""
        m = m or self.sample(rng)
        x = np.asarray(pa, dtype=np.float64)
        # corpo/pulso
        b, a = _biquad("lowshelf", 250, 0.7, m["body_low_db"]); x = sps.lfilter(b, a, x)
        b, a = _biquad("highshelf", 2500, 0.7, m["body_high_db"]); x = sps.lfilter(b, a, x)
        # par de microfones
        if m["dual_avg"]:
            x2 = frac_delay(x, m["mic_delay_us"] * 1e-6 * SR) * db2lin(m["mic_mismatch_db"])
            x = 0.5 * (x + x2)
        # MEMS: passa-altas (ventilação + acoplamento AC, 2a ordem total)
        sos = sps.butter(2, m["hpf_hz"], btype="high", fs=SR, output="sos")
        x = sps.sosfilt(sos, x)
        # ressonância da porta acústica / cavidade
        b, a = _biquad("peak", m["res_hz"], m["res_q"], m["res_gain_db"]); x = sps.lfilter(b, a, x)
        # saturação suave perto do AOP
        aop = spl_to_pa(m["aop_spl"]) * np.sqrt(2)
        x = aop * np.tanh(x / aop)
        n = len(x)
        calib = "floor_psd_db" in self.p
        if not calib:
            # ruído próprio do MEMS (branco + 1/f), nível a partir do SNR (ref 94 dB SPL)
            noise_spl = 94.0 - m["snr_dba"] + 1.5
            w = rng.standard_normal(n)
            pink = sps.lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786],
                               [1, -2.494956002, 2.017265875, -0.522189400], rng.standard_normal(n))
            nz = w / rms(w) + 0.5 * pink / (rms(pink) + 1e-12)
            x = x + nz / rms(nz) * spl_to_pa(noise_spl)
        # Pa -> fração do fundo de escala
        y = x / self.pa_per_fs(m)
        if calib:
            # piso de ruído MEDIDO no relógio (sala quieta + MEMS + elétrico), mesmo espectro e nível
            y = y + self._floor_noise(rng, n, m)
            for tone in self.p.get("tons", []):
                if rng.random() < 0.85:
                    t = np.arange(n) / SR
                    jit = 0.03 if tone["hz"] < 200 else 0.002
                    f0 = tone["hz"] * (1 + rng.uniform(-jit, jit))
                    lvl = tone["dbfs"] + (m["pga_db"] - 24) + rng.uniform(-4, 3)
                    y = y + db2lin(lvl) * np.sqrt(2) * np.sin(2 * np.pi * f0 * t + rng.uniform(0, 6.28))
        # espúrios elétricos (display/DC-DC/rádio) em nível baixo
        if m["spur"]:
            t = np.arange(n) / SR
            for _ in range(rng.integers(1, 4)):
                f = rng.uniform(60, 4000)
                y += db2lin(rng.uniform(-82, -60)) * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28))
            if rng.random() < 0.5:  # cliques periódicos (beacon Wi-Fi ~102.4 ms)
                per = int(0.1024 * SR)
                y[rng.integers(0, per)::per] += db2lin(rng.uniform(-75, -55)) * rng.choice([-1, 1])
        # ADC
        y = y + m["dc"]
        y = np.clip(y, -1.0, 1.0)  # sobrecarga do modulador (clipping analógico)
        sos = sps.cheby1(6, 0.1, m["lpf_hz"], btype="low", fs=SR, output="sos")
        y = sps.sosfilt(sos, y)  # filtro de decimação
        y = sps.lfilter([1, -1], [1, -0.9985], y)  # passa-altas digital (~4 Hz)
        q = np.clip(np.round(y * 32768), -32768, 32767).astype(np.int16)
        return q, m
