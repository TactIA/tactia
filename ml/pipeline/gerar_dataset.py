"""
Gera o dataset TactIA (janelas de 1 s, 16 kHz, int16) com o microfone do relógio simulado.
Split treino/teste por GRUPO DE ORIGEM (gravação / vídeo / locutor / instância sintética),
e os fundos usados na mistura também respeitam o split.

Uso: python3 gerar_dataset.py --saida /caminho/dataset [--perfil perfil_mic.json] [--escala 1.0]
"""
import argparse, json, os, collections, hashlib, time
import numpy as np, soundfile as sf, scipy.signal as sps
from concurrent.futures import ProcessPoolExecutor

import tactia_mic as M
import tactia_synth as S

SR = 16000
W = '/home/claude/work/'
CLASSES = ['alarme', 'ambiente', 'buzina', 'campainha', 'sirene']
TARGET = {'ambiente': 16000, 'sirene': 11600, 'alarme': 11600, 'buzina': 10000, 'campainha': 11600}
TEST_FRAC = 0.2
REAL_MAX_SHARE = {'sirene': 0.8, 'alarme': 0.72, 'buzina': 0.80, 'campainha': 0.70}
AMB_SYNTH = {'silencio': 0.07, 'motor': 0.04}
# nível do evento no relógio (dB SPL, RMS do trecho ativo)
# (mín, moda, máx) em dB SPL. Moda baixa: perto do que o relógio mediu nas suas sessões (~55-66 dB SPL),
# cauda até níveis de rua reais.
EVENT_SPL = {'sirene': (48, 64, 98), 'buzina': (50, 66, 98), 'alarme': (48, 62, 92), 'campainha': (46, 60, 86)}
P_SPEAKER = 0.25  # fração dos alertas reproduzidos por alto-falante pequeno (TV, celular, caixinha)
# ambientes acústicos por classe: (externo, interno, através da janela)
ENV_P = {'sirene': (0.55, 0.25, 0.20), 'buzina': (0.60, 0.20, 0.20), 'alarme': (0.12, 0.88, 0.0), 'campainha': (0.08, 0.92, 0.0)}
PRE = 0.6  # segundos de contexto antes da janela (cauda de reverberação e filtros)


_SPLIT = {}


def build_split_map(inv):
    """Split estratificado por (classe, dataset): ~20% dos GRUPOS de origem vão para teste
    (no mínimo 1 quando o bucket tem 2+ grupos). Determinístico (ordem por hash md5)."""
    buckets = collections.defaultdict(set)
    for it in inv:
        if it.get('force_split'):
            _SPLIT[it['group']] = it['force_split']
        elif it.get('valid'):
            buckets[(it['cls'], it['dataset'])].add(it['group'])
    for key, groups in buckets.items():
        gs = sorted(groups, key=lambda g: hashlib.md5(g.encode()).hexdigest())
        n_test = int(round(len(gs) * TEST_FRAC))
        if len(gs) >= 2:
            n_test = max(1, n_test)
        for i, g in enumerate(gs):
            _SPLIT.setdefault(g, 'test' if i < n_test else 'train')


def split_of(group, force=None):
    if force:
        return force
    return _SPLIT.get(group, 'train')


def load_seg(path, start, dur):
    info = sf.info(path)
    a = int(round(start * info.samplerate))
    b = a + int(round(dur * info.samplerate))
    x, fs = sf.read(path, start=max(a, 0), stop=min(b, info.frames), dtype='float32', always_2d=True)
    x = x.mean(1).astype(np.float64)
    if a < 0:
        x = np.concatenate([np.zeros(-a), x])
    need = int(round(dur * SR))
    if len(x) < need:
        x = np.pad(x, (0, need - len(x)))
    return x[:need]


def active_rms(x):
    """RMS só dos quadros ativos (até 10 dB abaixo do quadro mais forte)."""
    fr = 320
    n = len(x) // fr
    if n == 0:
        return M.rms(x)
    e = np.mean(x[: n * fr].reshape(n, fr) ** 2, axis=1) + 1e-20
    thr = e.max() / 10.0
    return float(np.sqrt(np.mean(e[e >= thr])))


def small_speaker(rng, x):
    """Caixinha/TV/celular: corta graves, realça médios, leve distorção."""
    sos = sps.butter(4, rng.uniform(120, 320), btype='high', fs=SR, output='sos')
    y = sps.sosfilt(sos, x)
    b, a = M._biquad('peak', rng.uniform(900, 3500), rng.uniform(0.7, 2.0), rng.uniform(1, 6))
    y = sps.lfilter(b, a, y)
    r = rng.random()
    if r < 0.35:
        y = sps.sosfilt(sps.butter(2, rng.uniform(5000, 7500), fs=SR, output='sos'), y)
    elif r < 0.8:  # brilho de tweeter
        b, a = M._biquad('peak', rng.uniform(5000, 7200), rng.uniform(1.0, 2.5), rng.uniform(3, 8))
        y = sps.lfilter(b, a, y)
    drive = rng.uniform(1.0, 3.0)
    pk = np.max(np.abs(y)) + 1e-12
    return np.tanh(drive * y / pk) / np.tanh(drive) * pk


def pick_env(rng, cls):
    pe, pi, pw = ENV_P[cls]
    r = rng.random()
    return 'externo' if r < pe else ('interno' if r < pe + pi else 'janela')


def apply_env(rng, x, env, is_real):
    """Aplica sala/externo. Fontes reais já têm acústica própria -> aplica mais leve e nem sempre."""
    info = {'amb': env}
    if env == 'interno':
        if (not is_real) or rng.random() < 0.5:
            h, ri = M.make_indoor_rir(rng)
            if is_real:  # evita reverberação excessiva sobre gravação já reverberante
                h = h * np.exp(-np.arange(len(h)) / (0.08 * SR))
            x = sps.fftconvolve(x, h)[: len(x)]
            info.update(ri)
    else:
        dist = float(np.exp(rng.uniform(np.log(3), np.log(250))))
        if (not is_real) or rng.random() < 0.6:
            h, ri = M.make_outdoor_rir(rng, dist)
            x = sps.fftconvolve(x, h)[: len(x)]
            info.update(ri)
        if env == 'janela':
            x = M.through_window(rng, x)
            h, ri = M.make_indoor_rir(rng)
            x = sps.fftconvolve(x, h * np.exp(-np.arange(len(h)) / (0.1 * SR)))[: len(x)]
    return x, info


class Pools:
    def __init__(self, inv):
        self.amb = {'train': collections.defaultdict(list), 'test': collections.defaultdict(list)}
        for it in inv:
            if it['cls'] == 'ambiente' and it['valid']:
                sp = split_of(it['group'], it.get('force_split'))
                self.amb[sp][self.amb_type(it)].append(it)

    @staticmethod
    def amb_type(it):
        if it.get('amb_tipo') in ('fala', 'casa', 'ruido'):
            return it['amb_tipo']
        return 'esc' if it['dataset'] == 'ESC-50' else 'audioset'

    def background(self, rng, split, dur, exclude_speech=False):
        types = ['audioset', 'esc', 'ruido', 'casa', 'fala']
        p = np.array([0.42, 0.14, 0.14, 0.15, 0.15])
        if exclude_speech:
            p[-1] = 0
        p = p / p.sum()
        t = types[rng.choice(len(types), p=p)]
        it = self.amb[split][t][rng.integers(len(self.amb[split][t]))]
        s = float(rng.choice(it['valid'])) + rng.uniform(-0.05, 0.05)
        x = load_seg(it['path'], s + 1.0 - dur, dur)
        if t == 'fala' and rng.random() < 0.8:
            h, _ = M.make_indoor_rir(rng)
            x = sps.fftconvolve(x, h)[: len(x)]
        return x, {'fundo': os.path.basename(it['path']), 'fundo_tipo': t}


def sample_snr(rng):
    if rng.random() < 0.08:
        return float(rng.uniform(-3, 0))
    return float(rng.triangular(0, 12, 35))


def render_target(rng, mic, pools, cls, split, src, is_real, meta):
    """src: trecho seco (PRE+1 s) com o evento terminando na janela final."""
    env = pick_env(rng, cls)
    falante = rng.random() < P_SPEAKER
    if falante:
        src = small_speaker(rng, src)
        env = 'interno' if env == 'janela' else env
    x, envinfo = apply_env(rng, src, env, is_real)
    envinfo['alto_falante'] = bool(falante)
    win = x[-SR:]
    ar = active_rms(win)
    if ar < 1e-9:
        return None
    spl = float(rng.triangular(*EVENT_SPL[cls]))
    if env == 'janela':
        spl -= rng.uniform(8, 22)
    x = x / ar * M.spl_to_pa(spl)
    total = x.copy()
    bg_info = {}
    snr = None
    if rng.random() < 0.9:
        bg, bg_info = pools.background(rng, split, len(x) / SR)
        snr = sample_snr(rng)
        bg_spl = float(np.clip(spl - snr, 25, 88))
        total = total + bg / (M.rms(bg[-SR:]) + 1e-12) * M.spl_to_pa(bg_spl)
        snr = spl - bg_spl
    q, m = mic(total, rng)
    meta.update(envinfo)
    meta.update(bg_info)
    meta.update({'spl_evento': round(spl, 1), 'snr_db': None if snr is None else round(snr, 1),
                 'pga_db': m['pga_db'], 'dois_mics': m['dual_avg']})
    return q[-SR:]


def render_ambient(rng, mic, pools, split, kind, item, meta):
    dur = PRE + 1.0
    if kind == 'silencio':
        x = np.zeros(int(dur * SR))
        if rng.random() < 0.6:
            bg, bi = pools.background(rng, split, dur, exclude_speech=True)
            x = bg / (M.rms(bg[-SR:]) + 1e-12) * M.spl_to_pa(rng.uniform(18, 34))
            meta.update(bi)
        meta['amb_sub'] = 'silencio'
    elif kind == 'motor':
        y, info = S.watch_vibration_motor(rng, dur=dur + 0.5)
        y = y[-int(dur * SR):]
        x = y / (active_rms(y[-SR:]) + 1e-12) * M.spl_to_pa(rng.uniform(55, 85))
        if rng.random() < 0.6:
            bg, bi = pools.background(rng, split, dur)
            x = x + bg / (M.rms(bg[-SR:]) + 1e-12) * M.spl_to_pa(rng.uniform(30, 65))
            meta.update(bi)
        meta['amb_sub'] = 'motor_vibracao'
    else:
        it = item
        s = float(rng.choice(it['valid'])) + rng.uniform(-0.05, 0.05)
        x = load_seg(it['path'], s + 1.0 - dur, dur)
        t = Pools.amb_type(it)
        if t == 'fala' and rng.random() < 0.85:
            h, _ = M.make_indoor_rir(rng)
            x = sps.fftconvolve(x, h)[: len(x)]
        lo, mo, hi = {'fala': (42, 55, 82), 'casa': (28, 40, 65), 'ruido': (38, 50, 85), 'esc': (38, 52, 88),
                      'audioset': (38, 52, 88)}[t]
        spl = float(rng.triangular(lo, mo, hi))
        x = x / (M.rms(x[-SR:]) + 1e-12) * M.spl_to_pa(spl)
        if rng.random() < 0.4:
            bg, bi = pools.background(rng, split, dur)
            x = x + bg / (M.rms(bg[-SR:]) + 1e-12) * M.spl_to_pa(spl - rng.uniform(0, 15))
            meta['fundo2'] = bi['fundo']
        meta.update({'amb_sub': t, 'spl_evento': round(spl, 1)})
    q, m = mic(x, rng)
    meta.update({'pga_db': m['pga_db'], 'dois_mics': m['dual_avg']})
    return q[-SR:]


SYNTH_TABLE = {'campainha': S.DOORBELL_SYNTHS, 'alarme': S.ALARM_SYNTHS, 'buzina': S.HORN_SYNTHS, 'sirene': S.SIREN_SYNTHS}


def synth_active_starts(y):
    fr = 160
    n = len(y) // fr
    e = np.mean(y[: n * fr].reshape(n, fr) ** 2, axis=1) + 1e-20
    act = e > e.max() * 10 ** (-2.5)
    W = 100
    cs = np.concatenate([[0], np.cumsum(act)])
    starts = []
    for s in range(0, max(1, n - W + 1), 5):
        if (cs[min(s + W, n)] - cs[s]) / W >= 0.2:
            starts.append(s * fr / SR)
    return starts


# ------------------------------------------------------------------ jobs
def job(args):
    """Processa uma lista de tarefas (mesmo worker), escreve WAVs, devolve metadados."""
    tasks, outdir, profile, seed = args
    rng = np.random.default_rng(seed)
    mic = M.WatchMic(profile)
    inv = json.load(open(W + 'inventario_validas.json'))
    build_split_map(inv)
    pools = Pools(inv)
    res = []
    for t in tasks:
        meta = {'classe': t['cls'], 'split': t['split'], 'origem': t['origem'], 'fonte': t.get('fonte', ''),
                'dataset': t.get('dataset', ''), 'licenca': t.get('licenca', ''), 'grupo': t.get('grupo', ''),
                'subtipo': t.get('subtipo', '')}
        trng = np.random.default_rng(t['seed'])
        q = None
        try:
            if t['kind'] == 'real_target':
                it = inv[t['item']]
                for _ in range(4):
                    s = float(trng.choice(it['valid'])) + trng.uniform(-0.06, 0.06)
                    s = min(max(s, 0.0), max(it['dur'] - 1.0, 0.0))
                    src = load_seg(it['path'], s - PRE, PRE + 1.0)
                    q = render_target(trng, mic, pools, t['cls'], t['split'], src, True, meta)
                    if q is not None:
                        meta['inicio_s'] = round(s, 2)
                        break
            elif t['kind'] == 'synth_target':
                fn = dict((f.__name__, f) for f, _ in SYNTH_TABLE[t['cls']])[t['fn']]
                y, info = fn(np.random.default_rng(t['inst_seed']))
                y = np.concatenate([np.zeros(int(PRE * SR)), y, np.zeros(int(0.3 * SR))])
                starts = [v for v in synth_active_starts(y) if v >= PRE] or [PRE]
                s = float(trng.choice(starts))
                src = y[int(round((s - PRE) * SR)):][: int((PRE + 1) * SR)]
                if len(src) < int((PRE + 1) * SR):
                    src = np.pad(src, (0, int((PRE + 1) * SR) - len(src)))
                meta['tipo_sintese'] = info['tipo']
                q = render_target(trng, mic, pools, t['cls'], t['split'], src, False, meta)
            elif t['kind'] == 'ambient':
                item = inv[t['item']] if t.get('item') is not None else None
                q = render_ambient(trng, mic, pools, t['split'], t['amb_kind'], item, meta)
        except Exception as e:
            meta['erro'] = repr(e)[:200]
            q = None
        if q is None:
            res.append(meta)
            continue
        cat = 'training' if t['split'] == 'train' else 'testing'
        fname = f"{t['cls']}.{t['split'][:2]}{t['idx']:06d}.wav"
        sf.write(os.path.join(outdir, cat, fname), q, SR, subtype='PCM_16')
        meta['arquivo'] = f'{cat}/{fname}'
        meta['pico_dbfs'] = round(20 * np.log10(np.abs(q).max() / 32768 + 1e-9), 1)
        meta['rms_dbfs'] = round(20 * np.log10(np.sqrt(np.mean((q / 32768.0) ** 2)) + 1e-9), 1)
        res.append(meta)
    return res


def plan(inv, scale, rng):
    tasks = []
    idx = collections.Counter()

    def add(**kw):
        key = (kw['cls'], kw['split'])
        kw['idx'] = idx[key]
        idx[key] += 1
        kw['seed'] = int(rng.integers(2 ** 62))
        tasks.append(kw)

    for cls in CLASSES:
        for split, frac in (('train', 1 - TEST_FRAC), ('test', TEST_FRAC)):
            n_total = int(round(TARGET[cls] * scale * frac))
            items = [(i, it) for i, it in enumerate(inv)
                     if it['cls'] == cls and it['valid'] and split_of(it['group'], it.get('force_split')) == split
                     and it.get('subtipo') != 'trem']  # buzina de trem atrapalhou a transferência p/ buzina de carro
            if cls == 'ambiente':
                n_sil = int(round(n_total * AMB_SYNTH['silencio']))
                n_mot = int(round(n_total * AMB_SYNTH['motor']))
                for _ in range(n_sil):
                    add(cls=cls, split=split, kind='ambient', amb_kind='silencio', item=None, origem='sintetico',
                        fonte='silencio+ruido_do_mic', grupo='sint')
                for _ in range(n_mot):
                    add(cls=cls, split=split, kind='ambient', amb_kind='motor', item=None, origem='sintetico',
                        fonte='motor_vibracao', grupo='sint')
                n_real = n_total - n_sil - n_mot
                # cota por tipo de ambiente
                share = {'audioset': 0.42, 'fala': 0.22, 'esc': 0.14, 'casa': 0.12, 'ruido': 0.10}
                by = collections.defaultdict(list)
                for i, it in items:
                    by[Pools.amb_type(it)].append((i, it))
                for t, sh in share.items():
                    k = int(round(n_real * sh))
                    pool = by[t]
                    w = np.array([min(len(it['valid']), 300) for _, it in pool], float)
                    choice = rng.choice(len(pool), size=k, p=w / w.sum())
                    for c in choice:
                        i, it = pool[c]
                        add(cls=cls, split=split, kind='ambient', amb_kind='real', item=i, origem='real',
                            fonte=os.path.basename(it['path']), dataset=it['dataset'], licenca=it['licenca'], grupo=it['group'])
                continue
            # classes-alvo: capacidade por fonte real
            cap = np.array([min(it.get('cap_max', 60 if cls == 'buzina' else 40), max(6, (1.2 if cls == 'buzina' else 0.8) * len(it['valid']))) for _, it in items], float)
            n_real = int(min(n_total * REAL_MAX_SHARE[cls], cap.sum()))
            if items and n_real > 0:
                alloc = np.floor(cap / cap.sum() * n_real).astype(int)
                rem = n_real - alloc.sum()
                if rem > 0:
                    extra = rng.choice(len(items), size=rem, p=cap / cap.sum())
                    for e in extra:
                        alloc[e] += 1
                for (i, it), k in zip(items, alloc):
                    for _ in range(k):
                        add(cls=cls, split=split, kind='real_target', item=i, origem='real', subtipo=it.get('subtipo', ''),
                            fonte=os.path.basename(it['path']), dataset=it['dataset'], licenca=it['licenca'], grupo=it['group'])
            n_syn = n_total - n_real
            if n_syn > 0:
                table = SYNTH_TABLE[cls]
                fns, ps = zip(*table)
                ps = np.array(ps) / sum(ps)
                per_inst = 3
                for j in range(int(np.ceil(n_syn / per_inst))):
                    fn = fns[rng.choice(len(fns), p=ps)]
                    inst_seed = int(rng.integers(2 ** 62)) ^ (0 if split == 'train' else 0x5A5A5A5A)
                    for _ in range(min(per_inst, n_syn - j * per_inst)):
                        add(cls=cls, split=split, kind='synth_target', fn=fn.__name__, inst_seed=inst_seed,
                            origem='sintetico', fonte=fn.__name__, dataset='síntese física (TactIA)', licenca='gerado (livre)',
                            grupo=f'sint:{split}:{inst_seed}')
    return tasks


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--saida', required=True)
    ap.add_argument('--perfil', default=None)
    ap.add_argument('--escala', type=float, default=1.0)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--seed', type=int, default=2026)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.saida, 'training'), exist_ok=True)
    os.makedirs(os.path.join(a.saida, 'testing'), exist_ok=True)
    profile = M.load_profile(a.perfil)
    rng = np.random.default_rng(a.seed)
    inv = json.load(open(W + 'inventario_validas.json'))
    build_split_map(inv)
    tasks = plan(inv, a.escala, rng)
    rng.shuffle(tasks)
    print('tarefas', len(tasks), collections.Counter((t['cls'], t['split'], t['origem']) for t in tasks), flush=True)
    chunks = [tasks[i::a.workers * 8] for i in range(a.workers * 8)]
    t0 = time.time()
    metas = []
    with ProcessPoolExecutor(a.workers) as ex:
        for k, r in enumerate(ex.map(job, [(c, a.saida, profile, a.seed + i) for i, c in enumerate(chunks)])):
            metas.extend(r)
            print(f'bloco {k + 1}/{len(chunks)}  {time.time() - t0:.0f}s', flush=True)
    json.dump(metas, open(os.path.join(a.saida, 'metadados_completos.json'), 'w'), ensure_ascii=False)
    print('ok', sum(1 for m in metas if 'arquivo' in m), 'erros', sum(1 for m in metas if 'erro' in m))
