"""Gera info.labels (Edge Impulse), manifesto CSV e checagens de vazamento/contagem."""
import json, csv, os, sys, collections
import numpy as np

out = sys.argv[1]
metas = json.load(open(os.path.join(out, 'metadados_completos.json')))
ok = [m for m in metas if 'arquivo' in m]

# MS-SNSD tem nomes repetidos entre noise_train/ e noise_test/ (arquivos DIFERENTES, mesmo nome).
# Como o split dessas fontes é forçado pela pasta, o caminho real é determinado pelo split da janela.
import glob
SNSD = {os.path.basename(p) for p in glob.glob('/home/claude/src/mssnsd/noise_*/*.wav')}
for m in ok:
    pre = 'noise_train/' if m['split'] == 'train' else 'noise_test/'
    if m.get('dataset', '').startswith('MS-SNSD') and '/' not in m['fonte']:
        m['fonte'] = pre + m['fonte']
        m['grupo'] = 'snsd:' + m['fonte']
    if m.get('grupo') == 'sint':
        m['grupo'] = 'sint:' + m['arquivo']
    if m.get('dataset', '') == '' and m['origem'] == 'sintetico':
        m['dataset'], m['licenca'] = 'síntese física (TactIA)', 'gerado (livre)'
    if m.get('dataset', '').startswith('MS-SNSD'):
        m['licenca'] = 'CC0 (Freesound) / CC BY-SA 3.0 (DEMAND)'
    for k in ('fundo', 'fundo2'):
        if m.get(k) in SNSD and '/' not in m[k]:
            m[k] = pre + m[k]
json.dump(metas, open(os.path.join(out, 'metadados_completos.json'), 'w'), ensure_ascii=False)
err = [m for m in metas if 'arquivo' not in m]
print('arquivos', len(ok), 'falhas', len(err))

# ---------- vazamento: nenhum grupo de origem (nem fundo) em treino e teste ----------
g_split = collections.defaultdict(set)
bg_split = collections.defaultdict(set)
for m in ok:
    if m['grupo'] and not m['grupo'].startswith('sint'):
        g_split[m['grupo']].add(m['split'])
    for k in ('fundo', 'fundo2'):
        if m.get(k):
            bg_split[m[k]].add(m['split'])
leak_g = [g for g, s in g_split.items() if len(s) > 1]
leak_bg = [g for g, s in bg_split.items() if len(s) > 1]
# fonte usada como evento em um split e como fundo no outro?
src_split = collections.defaultdict(set)
for m in ok:
    if m['origem'] == 'real':
        src_split[m['fonte']].add(m['split'])
cross = [f for f in bg_split if f in src_split and (bg_split[f] | src_split[f]) == {'train', 'test'}]
print('grupos em treino E teste:', len(leak_g), '| fundos em treino E teste:', len(leak_bg), '| fonte/fundo cruzados:', len(cross))
assert not leak_g and not leak_bg and not cross, 'VAZAMENTO DETECTADO'

# ---------- info.labels ----------
files = []
for m in ok:
    md = {
        'origem': m['origem'],
        'dataset': m.get('dataset', ''),
        'fonte': m.get('fonte', '')[:60],
        'grupo': m.get('grupo', '')[:60],
        'gravacao': m.get('grupo', '')[:60],  # mesma chave do dataset do relógio: validação separada por gravação
        'sessao': 'publico_simulado_v3',
        'alto_falante': str(m.get('alto_falante', '')),
        'tipo': m.get('tipo_sintese', m.get('amb_sub', '')),
        'ambiente_acustico': m.get('amb', ''),
        'spl_db': str(m.get('spl_evento', '')),
        'snr_db': str(m.get('snr_db', '')),
        'pga_db': str(m.get('pga_db', '')),
    }
    files.append({'path': m['arquivo'], 'category': 'training' if m['split'] == 'train' else 'testing',
                  'label': {'type': 'label', 'label': m['classe']}, 'metadata': md})
json.dump({'version': 1, 'files': files}, open(os.path.join(out, 'info.labels'), 'w'), ensure_ascii=False)

# ---------- manifesto ----------
cols = ['arquivo', 'classe', 'split', 'origem', 'dataset', 'licenca', 'fonte', 'grupo', 'tipo_sintese', 'amb_sub', 'amb',
        'rt60', 'dist_m', 'spl_evento', 'snr_db', 'fundo', 'fundo_tipo', 'pga_db', 'dois_mics', 'rms_dbfs', 'pico_dbfs']
with open(os.path.join(out, 'manifesto.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
    w.writeheader()
    for m in sorted(ok, key=lambda x: x['arquivo']):
        w.writerow(m)

# ---------- resumo ----------
tab = collections.Counter((m['classe'], m['split'], m['origem']) for m in ok)
srcs = collections.defaultdict(set)
for m in ok:
    if m['origem'] == 'real':
        srcs[(m['classe'], m['split'])].add(m['grupo'])
lines = ['classe,split,real,sintetico,total,fontes_reais_distintas']
for c in ['alarme', 'ambiente', 'buzina', 'campainha', 'sirene']:
    for s in ['train', 'test']:
        r, y = tab[(c, s, 'real')], tab[(c, s, 'sintetico')]
        lines.append(f'{c},{s},{r},{y},{r + y},{len(srcs[(c, s)])}')
open(os.path.join(out, 'resumo.csv'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
clip = collections.defaultdict(list)
for m in ok:
    clip[m['classe']].append(m['pico_dbfs'] > -0.1)
print({k: f'{100 * np.mean(v):.1f}% clip' for k, v in clip.items()})
lic = collections.Counter((m.get('dataset', ''), m.get('licenca', '')) for m in ok)
for k, v in lic.most_common():
    print(v, k)
