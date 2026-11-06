"""
Sintetizadores procedurais (modelos físicos simplificados) para as classes
campainha, alarme e buzina. Tudo a 16 kHz, mantendo parciais abaixo de ~7.5 kHz.

Cada função recebe um numpy Generator e devolve (audio_float32, info_dict).
O áudio sai "seco" (sem sala, sem microfone): a sala e o microfone do relógio
são aplicados depois pelo simulador.
"""

import numpy as np
import scipy.signal as sps

SR = 16000
NYQ_SAFE = 7400.0


def _t(n):
    return np.arange(n) / SR


def _env_adsr(n, a, d, s, r, sustain_len):
    """Envelope ADSR em amostras."""
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    sl = int(sustain_len * SR)
    env = np.concatenate(
        [
            np.linspace(0, 1, max(a, 1), endpoint=False),
            np.linspace(1, s, max(d, 1), endpoint=False),
            np.full(max(sl, 0), s),
            np.linspace(s, 0, max(r, 1)),
        ]
    )
    out = np.zeros(n, dtype=np.float64)
    m = min(n, len(env))
    out[:m] = env[:m]
    return out


def _place(buf, x, start):
    s = int(start * SR)
    if s >= len(buf):
        return
    m = min(len(x), len(buf) - s)
    buf[s : s + m] += x[:m]


def _strike_click(rng, dur=0.004, fc=(1500, 5000)):
    n = int(dur * SR)
    noise = rng.standard_normal(n) * np.exp(-np.linspace(0, 6, n))
    lo, hi = fc
    sos = sps.butter(2, [lo, min(hi, NYQ_SAFE)], btype="band", fs=SR, output="sos")
    return sps.sosfilt(sos, noise)


def _modal_tone(rng, f0, ratios, amps, t60s, dur, detune=0.003):
    """Soma de modos amortecidos (barra/tubo/sino golpeado)."""
    n = int(dur * SR)
    t = _t(n)
    y = np.zeros(n)
    for r, a, t60 in zip(ratios, amps, t60s):
        f = f0 * r * (1 + rng.normal(0, detune))
        if f >= NYQ_SAFE:
            continue
        ph = rng.uniform(0, 2 * np.pi)
        decay = np.exp(-6.91 * t / max(t60, 1e-3))
        # leve batimento entre modos degenerados (realismo de metal)
        beat = 1 + 0.15 * rng.random() * np.sin(2 * np.pi * rng.uniform(0.5, 4) * t)
        y += a * decay * beat * np.sin(2 * np.pi * f * t + ph)
    return y


# --------------------------------------------------------------------------
# CAMPAINHA
# --------------------------------------------------------------------------
BAR_RATIOS = [1.0, 2.756, 5.404, 8.933]  # barra livre-livre
TUBE_RATIOS = [1.0, 2.76, 5.40, 8.93, 13.34]  # tubo (aprox.)


def NOTE(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


MELODIES = {
    "dingdong": [(76, 0.0), (72, 0.55)],
    "dingdong_dingdong": [(76, 0.0), (72, 0.5), (76, 1.2), (72, 1.7)],
    "westminster": [(76, 0.0), (72, 0.45), (74, 0.9), (67, 1.35), (67, 2.1), (74, 2.55), (76, 3.0), (72, 3.45)],
    "tres_notas": [(79, 0.0), (76, 0.35), (72, 0.7)],
    "arpejo": [(72, 0.0), (76, 0.18), (79, 0.36), (84, 0.54)],
    "ding_dong_ding": [(76, 0.0), (72, 0.45), (76, 0.9)],
    "descendente": [(84, 0.0), (81, 0.2), (77, 0.4), (72, 0.6)],
    "big_ben": [(71, 0.0), (67, 0.5), (69, 1.0), (62, 1.5)],
    "fur_elise": [
        (76, 0.0),
        (75, 0.18),
        (76, 0.36),
        (75, 0.54),
        (76, 0.72),
        (71, 0.9),
        (74, 1.08),
        (72, 1.26),
        (69, 1.44),
    ],
}


def doorbell_mechanical(rng):
    """Ding-dong de solenoide batendo em barras metálicas."""
    transpose = rng.uniform(-4, 4)
    base = [(76, 0.0), (72, rng.uniform(0.35, 0.9))]
    if rng.random() < 0.25:
        base.append((76 + rng.choice([0, 3, 4, 7]), base[1][1] + rng.uniform(0.3, 0.8)))
    presses = 1 + int(rng.random() < 0.35) + int(rng.random() < 0.1)
    dur = 0.4 + presses * (base[-1][1] + 1.6)
    y = np.zeros(int(dur * SR))
    t0 = rng.uniform(0.05, 0.3)
    ratios = BAR_RATIOS if rng.random() < 0.6 else TUBE_RATIOS
    for _ in range(presses):
        for midi, off in base:
            f0 = NOTE(midi + transpose)
            amps = [1.0, rng.uniform(0.2, 0.6), rng.uniform(0.05, 0.3), rng.uniform(0.0, 0.15), rng.uniform(0, 0.08)]
            t60 = rng.uniform(1.0, 3.5)
            t60s = [t60, t60 * 0.35, t60 * 0.15, t60 * 0.08, t60 * 0.05]
            tone = _modal_tone(rng, f0, ratios, amps, t60s, 2.5)
            tone[: int(0.004 * SR)] += _strike_click(rng) * rng.uniform(0.2, 0.8)
            _place(y, tone, t0 + off)
        t0 += base[-1][1] + rng.uniform(0.9, 1.6)
    return y, {"tipo": "mecanica_dingdong"}


def doorbell_electronic(rng):
    """Campainha eletrônica / sem fio com melodia."""
    name = rng.choice(list(MELODIES))
    mel = MELODIES[name]
    transpose = rng.uniform(-7, 7)
    tempo = rng.uniform(0.75, 1.35)
    timbre = rng.choice(["seno", "fm_sino", "quadrada", "seno_harm"])
    note_dur = rng.uniform(0.25, 1.2)
    total = mel[-1][1] * tempo + note_dur + 0.5
    reps = 1 + int(rng.random() < 0.25)
    y = np.zeros(int((total * reps + 0.4) * SR))
    t0 = rng.uniform(0.05, 0.3)
    for _ in range(reps):
        for midi, off in mel:
            f = NOTE(midi + transpose)
            n = int(note_dur * SR * 1.6)
            t = _t(n)
            dec = np.exp(-t / (note_dur * rng.uniform(0.25, 0.6)))
            att = np.minimum(1, t / rng.uniform(0.002, 0.015))
            if timbre == "seno":
                x = np.sin(2 * np.pi * f * t)
            elif timbre == "seno_harm":
                x = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
            elif timbre == "fm_sino":
                ratio = rng.choice([1.4, 2.0, 3.5, 1.0])
                idx = rng.uniform(1, 5) * np.exp(-t / rng.uniform(0.1, 0.5))
                x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * ratio * t))
            else:  # quadrada limitada em banda (buzzer piezo barato)
                x = np.zeros(n)
                k = 1
                while f * k < NYQ_SAFE and k < 25:
                    x += np.sin(2 * np.pi * f * k * t) / k
                    k += 2
            _place(y, (x * dec * att), t0 + off * tempo)
        t0 += total
    return y, {"tipo": f"eletronica_{name}_{timbre}"}


def doorbell_buzzer(rng):
    """'Cigarra' eletromecânica (muito comum no Brasil): zumbido a 2x a rede (60 Hz -> 120 Hz)."""
    mains = 60.0 if rng.random() < 0.85 else 50.0
    f0 = 2 * mains * (1 + rng.normal(0, 0.01))
    presses = rng.integers(1, 4)
    segs = []
    for _ in range(presses):
        segs.append((rng.uniform(0.3, 2.5), rng.uniform(0.15, 0.8)))
    total = sum(a + b for a, b in segs) + 0.4
    y = np.zeros(int(total * SR))
    t0 = rng.uniform(0.05, 0.25)
    for on, off in segs:
        n = int(on * SR)
        t = _t(n)
        # armadura batendo: pulso estreito periódico + ruído de vibração
        duty = rng.uniform(0.08, 0.3)
        phase = (f0 * t) % 1.0
        pulse = (phase < duty).astype(float) - duty
        rattle = rng.standard_normal(n) * (phase < duty * 1.5) * rng.uniform(0.1, 0.5)
        x = pulse + rattle
        # ressonância da caixa
        fr = rng.uniform(900, 3200)
        sos = sps.butter(2, [fr / 1.8, min(fr * 1.8, NYQ_SAFE)], btype="band", fs=SR, output="sos")
        x = 0.6 * sps.sosfilt(sos, x) + 0.4 * x
        x *= _env_adsr(n, 0.01, 0.02, 1.0, 0.03, on - 0.06)
        _place(y, x, t0)
        t0 += on + off
    return y, {"tipo": "cigarra"}


def doorbell_bell_ringer(rng):
    """Campainha de sino eletromecânica (martelo batendo no gongo, 'trimmm')."""
    f0 = rng.uniform(700, 2600)
    ratios = [1.0, rng.uniform(1.9, 2.3), rng.uniform(3.0, 3.6), rng.uniform(4.6, 5.6), rng.uniform(6.5, 7.6)]
    rate = rng.uniform(14, 28)
    on = rng.uniform(0.6, 3.0)
    total = on + 2.0
    y = np.zeros(int(total * SR))
    t0 = rng.uniform(0.05, 0.2)
    nstrikes = int(on * rate)
    amps = [1.0, 0.6, 0.4, 0.25, 0.15]
    t60 = rng.uniform(0.6, 2.0)
    for i in range(nstrikes):
        tone = _modal_tone(
            rng,
            f0,
            ratios,
            [a * rng.uniform(0.7, 1.0) for a in amps],
            [t60, t60 * 0.6, t60 * 0.4, t60 * 0.25, t60 * 0.15],
            0.6,
            detune=0.0005,
        )
        tone[: int(0.003 * SR)] += _strike_click(rng, 0.003) * 0.5
        _place(y, tone * rng.uniform(0.8, 1.0), t0 + i / rate + rng.normal(0, 0.002))
    return y, {"tipo": "sino_eletromecanico"}


def doorbell_twotone(rng):
    """Ding-dong eletrônico simples de dois tons (seno com decaimento)."""
    f1 = rng.uniform(500, 1400)
    f2 = f1 * rng.choice([0.8, 0.75, 0.84, 0.667])
    gap = rng.uniform(0.3, 0.8)
    dec = rng.uniform(0.3, 1.2)
    total = gap + dec * 4 + 0.4
    y = np.zeros(int(total * SR))
    for f, off in [(f1, 0.1), (f2, 0.1 + gap)]:
        n = int(dec * 4 * SR)
        t = _t(n)
        x = (np.sin(2 * np.pi * f * t) + rng.uniform(0, 0.3) * np.sin(4 * np.pi * f * t)) * np.exp(-t / dec)
        x *= np.minimum(1, t / 0.005)
        _place(y, x, off)
    return y, {"tipo": "dois_tons"}


DOORBELL_SYNTHS = [
    (doorbell_mechanical, 0.27),
    (doorbell_electronic, 0.30),
    (doorbell_buzzer, 0.18),
    (doorbell_bell_ringer, 0.10),
    (doorbell_twotone, 0.15),
]


# --------------------------------------------------------------------------
# ALARME
# --------------------------------------------------------------------------
def _piezo_tone(rng, f, n):
    t = _t(n)
    fm = f * (1 + 0.004 * np.sin(2 * np.pi * rng.uniform(5, 40) * t))
    ph = 2 * np.pi * np.cumsum(fm) / SR
    x = np.sin(ph)
    # piezo produz forma quase quadrada; harmônicos ímpares limitados em banda
    k = 3
    while f * k < NYQ_SAFE:
        x += rng.uniform(0.05, 0.3) / k * np.sin(k * ph)
        k += 2
    return x


def alarm_smoke_t3(rng):
    """Detector de fumaça (padrão temporal T3) ou de CO (T4)."""
    f = rng.uniform(2900, 3500) if rng.random() < 0.75 else rng.uniform(2000, 2900)
    co = rng.random() < 0.2
    beep, gap = (0.1, 0.1) if co else (rng.uniform(0.45, 0.55), rng.uniform(0.45, 0.55))
    nb = 4 if co else 3
    long_gap = rng.uniform(1.4, 1.6) if not co else rng.uniform(4.5, 5.2)
    cycles = rng.integers(2, 4)
    total = cycles * (nb * (beep + gap) + long_gap) + 0.3
    y = np.zeros(int(total * SR))
    t0 = rng.uniform(0.0, 0.3)
    for _ in range(cycles):
        for _ in range(nb):
            n = int(beep * SR)
            x = _piezo_tone(rng, f, n) * _env_adsr(n, 0.003, 0.005, 1, 0.005, beep - 0.013)
            _place(y, x, t0)
            t0 += beep + gap
        t0 += long_gap - gap
    return y, {"tipo": "detector_fumaca_co" if co else "detector_fumaca_t3"}


def alarm_digital_clock(rng):
    """Despertador digital: grupos de bipes agudos."""
    f = rng.uniform(1800, 4200)
    nb = rng.integers(2, 6)
    beep = rng.uniform(0.04, 0.12)
    gap = rng.uniform(0.04, 0.12)
    grp_gap = rng.uniform(0.3, 0.9)
    groups = rng.integers(3, 8)
    total = groups * (nb * (beep + gap) + grp_gap) + 0.3
    y = np.zeros(int(total * SR))
    t0 = rng.uniform(0, 0.3)
    for _ in range(groups):
        for _ in range(nb):
            n = int(beep * SR)
            _place(y, _piezo_tone(rng, f, n) * _env_adsr(n, 0.002, 0.003, 1, 0.003, beep - 0.008), t0)
            t0 += beep + gap
        t0 += grp_gap
    return y, {"tipo": "despertador_digital"}


def alarm_mechanical_clock(rng):
    """Despertador mecânico de duas campânulas (martelo ~20-30 Hz)."""
    rate = rng.uniform(18, 32)
    on = rng.uniform(1.5, 4.0)
    f1, f2 = rng.uniform(1600, 3000), rng.uniform(1600, 3000)
    ratios = [1.0, 2.32, 4.25, 6.63]
    total = on + 1.0
    y = np.zeros(int(total * SR))
    for i in range(int(on * rate)):
        f = f1 if i % 2 == 0 else f2
        tone = _modal_tone(rng, f, ratios, [1, 0.5, 0.25, 0.1], [0.5, 0.25, 0.12, 0.06], 0.35, detune=0.001)
        tone[: int(0.002 * SR)] += _strike_click(rng, 0.002) * 0.6
        _place(y, tone, 0.1 + i / rate)
    return y, {"tipo": "despertador_mecanico"}


def alarm_fire_horn(rng):
    """Sirene/buzzer de alarme de incêndio (buzina eletrônica pulsada ou 'whoop')."""
    kind = rng.choice(["buzz", "whoop", "slow_whoop", "bell_tone"])
    total = rng.uniform(3, 6)
    n = int(total * SR)
    t = _t(n)
    if kind == "buzz":
        f0 = rng.uniform(400, 1000)
        ph = 2 * np.pi * f0 * t
        x = sum(np.sin(k * ph) / k for k in range(1, 15) if f0 * k < NYQ_SAFE)
        rate = rng.uniform(1, 3)
        gate = ((t * rate) % 1.0 < rng.uniform(0.4, 0.7)).astype(float)
        x *= sps.lfilter([0.02], [1, -0.98], gate)
    elif kind in ("whoop", "slow_whoop"):
        per = rng.uniform(0.6, 1.2) if kind == "whoop" else rng.uniform(2, 4)
        f = rng.uniform(500, 900) + rng.uniform(600, 1800) * ((t % per) / per)
        ph = 2 * np.pi * np.cumsum(f) / SR
        x = np.sin(ph) + 0.3 * np.sin(3 * ph)
    else:
        f = rng.uniform(2000, 3200)
        x = _piezo_tone(rng, f, n) * (((t * rng.uniform(1.5, 4)) % 1) < 0.5)
    return x, {"tipo": f"alarme_incendio_{kind}"}


ALARM_SYNTHS = [
    (alarm_smoke_t3, 0.35),
    (alarm_digital_clock, 0.30),
    (alarm_mechanical_clock, 0.15),
    (alarm_fire_horn, 0.20),
]


# --------------------------------------------------------------------------
# BUZINA
# --------------------------------------------------------------------------
def _horn_voice(rng, f0, n, brightness):
    """Buzina eletromagnética de disco: diafragma batendo -> forma de pulso rica."""
    jitter = 1 + 0.003 * sps.lfilter([0.01], [1, -0.99], rng.standard_normal(n))
    ph = 2 * np.pi * np.cumsum(f0 * jitter) / SR
    x = np.zeros(n)
    k = 1
    while f0 * k < NYQ_SAFE:
        x += (brightness ** (k - 1)) * np.sin(k * ph + rng.uniform(0, 0.3))
        k += 1
    return x


def horn_car(rng):
    kind = rng.choice(["carro_dupla", "carro_simples", "caminhao_ar", "moto"], p=[0.5, 0.2, 0.18, 0.12])
    if kind == "carro_dupla":
        fs = [rng.uniform(380, 440), rng.uniform(470, 540)]
    elif kind == "carro_simples":
        fs = [rng.uniform(350, 520)]
    elif kind == "caminhao_ar":
        base = rng.uniform(180, 330)
        fs = [base, base * rng.choice([1.26, 1.33, 1.5]), base * rng.choice([1.5, 1.68, 2.0])][: rng.integers(1, 4)]
    else:
        fs = [rng.uniform(420, 650)]
    pattern = rng.choice(["curta", "dupla", "longa", "tripla"], p=[0.3, 0.3, 0.25, 0.15])
    if pattern == "curta":
        hits = [(0.1, rng.uniform(0.15, 0.45))]
    elif pattern == "dupla":
        d = rng.uniform(0.1, 0.3)
        hits = [(0.1, d), (0.1 + d + rng.uniform(0.08, 0.2), d)]
    elif pattern == "tripla":
        d = rng.uniform(0.08, 0.2)
        g = rng.uniform(0.07, 0.15)
        hits = [(0.1 + i * (d + g), d) for i in range(3)]
    else:
        hits = [(0.1, rng.uniform(0.8, 3.0))]
    total = hits[-1][0] + hits[-1][1] + 0.5
    y = np.zeros(int(total * SR))
    bright = rng.uniform(0.55, 0.85)
    for start, dur in hits:
        n = int(dur * SR)
        v = sum(_horn_voice(rng, f, n, bright) * rng.uniform(0.7, 1.0) for f in fs)
        # ressonância da corneta
        for fr in rng.uniform(900, 3500, size=2):
            b, a = sps.iirpeak(min(fr, NYQ_SAFE), rng.uniform(1.5, 4), fs=SR)
            v = v + rng.uniform(0.3, 1.0) * sps.lfilter(b, a, v)
        v *= _env_adsr(n, rng.uniform(0.008, 0.03), 0.02, 0.9, rng.uniform(0.01, 0.04), dur - 0.08)
        _place(y, v, start)
    # Doppler leve (veículo passando)
    if rng.random() < 0.3:
        shift = rng.uniform(-0.04, 0.04)
        n = len(y)
        warp = np.cumsum(1 + shift * np.linspace(1, -1, n))
        warp = warp / warp[-1] * (n - 1)
        y = np.interp(warp, np.arange(n), y)
    return y, {"tipo": f"buzina_{kind}_{pattern}"}


HORN_SYNTHS = [(horn_car, 1.0)]


# --------------------------------------------------------------------------
# AMBIENTE: motor de vibração do próprio relógio (falsos positivos pós-alerta)
# --------------------------------------------------------------------------
def watch_vibration_motor(rng, dur=3.0):
    """ERM tipo 'vibracall' (~9-14k rpm -> 150-230 Hz) acoplado mecanicamente ao mic."""
    n = int(dur * SR)
    t = _t(n)
    f0 = rng.uniform(140, 240)
    ramp = np.minimum(1, t / rng.uniform(0.03, 0.12))
    f = f0 * (0.6 + 0.4 * ramp)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.3 * np.sin(3 * ph) + 0.15 * np.sin(5 * ph)
    rattle = rng.standard_normal(n) * (np.sin(ph) > 0.7)
    rattle = sps.sosfilt(sps.butter(2, rng.uniform(600, 1800), fs=SR, output="sos"), rattle)
    x += rng.uniform(0.02, 0.12) * rattle / (np.std(rattle) + 1e-9)  # chocalho mecânico
    x = sps.sosfilt(sps.butter(2, rng.uniform(1200, 3000), fs=SR, output="sos"), x)
    on = rng.uniform(0.15, 0.6)
    off = rng.uniform(0.1, 0.5)
    gate = ((t % (on + off)) < on).astype(float)
    gate = sps.lfilter([0.05], [1, -0.95], gate)
    return x * ramp * gate, {"tipo": "motor_vibracao_relogio"}


def pick(rng, table):
    fns, ps = zip(*table)
    ps = np.array(ps) / sum(ps)
    return fns[rng.choice(len(fns), p=ps)]


# --------------------------------------------------------------------------
# SIRENE eletrônica (ambulância/polícia/bombeiro): onda quadrada em corneta
# --------------------------------------------------------------------------
def siren_electronic(rng):
    kind = rng.choice(["wail", "yelp", "hilo", "phaser", "wail_yelp"], p=[0.3, 0.3, 0.2, 0.08, 0.12])
    dur = rng.uniform(3.0, 6.0)
    n = int(dur * SR)
    t = np.arange(n) / SR
    flo, fhi = rng.uniform(450, 800), rng.uniform(1150, 1800)

    def sweep(per, shape):
        ph = (t / per + rng.uniform(0, 1)) % 1.0
        if shape == "tri":
            u = np.where(ph < 0.5, ph * 2, 2 - ph * 2)
        else:  # sobe devagar, desce rápido
            r = rng.uniform(0.55, 0.8)
            u = np.where(ph < r, ph / r, 1 - (ph - r) / (1 - r))
        return flo + (fhi - flo) * u

    if kind == "wail":
        f = sweep(rng.uniform(2.5, 6.0), "asym")
    elif kind == "yelp":
        f = sweep(rng.uniform(0.2, 0.45), "tri")
    elif kind == "phaser":
        f = sweep(rng.uniform(0.06, 0.12), "tri")
    elif kind == "hilo":
        a, b = rng.uniform(400, 700), 0
        b = a * rng.choice([1.26, 1.33, 1.4])
        per = rng.uniform(0.9, 1.5)
        f = np.where(((t / per) % 1.0) < 0.5, a, b)
        f = sps.lfilter([0.02], [1, -0.98], f) if rng.random() < 0.5 else f
    else:
        cut = rng.uniform(0.3, 0.7) * n
        f = np.where(np.arange(n) < cut, sweep(rng.uniform(3, 5), "asym"), sweep(rng.uniform(0.2, 0.4), "tri"))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.zeros(n)
    k = 1
    duty_odd = rng.random() < 0.7
    while k < 30:
        if np.all(f * k > NYQ_SAFE):
            break
        amp = (1.0 / k) * (f * k < NYQ_SAFE)
        if duty_odd and k % 2 == 0:
            amp = amp * rng.uniform(0.0, 0.15)
        x += amp * np.sin(k * ph)
        k += 1
    # corneta/alto-falante da sirene
    for fr in rng.uniform(800, 3000, size=2):
        b, a = sps.iirpeak(fr, rng.uniform(1.0, 3.0), fs=SR)
        x = x + rng.uniform(0.3, 1.0) * sps.lfilter(b, a, x)
    x *= np.minimum(1, t / 0.05)
    return x, {"tipo": f"sirene_{kind}"}


SIREN_SYNTHS = [(siren_electronic, 1.0)]
