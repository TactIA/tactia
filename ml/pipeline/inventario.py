"""Monta o inventário de fontes reais (com grupo de origem para o split) e as listas para etiquetagem."""
import json, csv, glob, os, re, collections, random
import soundfile as sf

random.seed(11)
W = '/home/claude/work/'
items = []


def add(cls, path, dataset, group, licenca, extra=None):
    d = {'cls': cls, 'path': path, 'dataset': dataset, 'group': group, 'licenca': licenca, 'kind': 'real'}
    if extra:
        d.update(extra)
    items.append(d)


# ---- AudioSet via DNS Challenge (Microsoft) ------------------------------------
sel = json.load(open(W + 'dns_selected.json'))
strong = json.load(open(W + 'dns_strong.json'))
TGT = {
    'sirene': {'/m/03kmc9', '/m/04qvtq', '/m/012n7d', '/m/012ndj', '/m/0dgbq', '/m/03j1ly'},
    'buzina': {'/m/0912c9', '/m/05x_td', '/m/07qv_d5'},
    'alarme': {'/m/07pp_mv', '/m/046dlr', '/m/01y3hg', '/m/0c3f7m', '/m/02mfyn'},
    'campainha': {'/m/03wwcy', '/m/07r67yg', '/m/07phxs1'},
}
for y, c in sel.items():
    p = f'/home/claude/raw/dns/{y}.wav'
    if not os.path.exists(p):
        continue
    ex = {}
    if c in TGT and y in strong:
        iv = [(on, off) for (l, on, off) in strong[y] if l in TGT[c]]
        if iv:
            ex['strong'] = iv
    add(c, p, 'AudioSet (via DNS Challenge 2020)', 'as:' + y, 'CC BY 4.0', ex)

# ---- Buzinas de trem (AudioSet 'Train horn'), como fontes extras de buzina ---------
for y in [l.strip() for l in open(W + 'trainhorn_dl.txt') if l.strip()]:
    p = f'/home/claude/raw/dns/{y}.wav'
    if not os.path.exists(p):
        continue
    ex = {'subtipo': 'trem', 'cap_max': 15}
    if y in strong:
        iv = [(on, off) for (l, on, off) in strong[y] if l == '/m/0284vy3']
        if iv:
            ex['strong'] = iv
    add('buzina', p, 'AudioSet (via DNS Challenge 2020)', 'as:' + y, 'CC BY 4.0', ex)

# ---- ESC-50 ---------------------------------------------------------------------
ESC_MAP = {'car_horn': 'buzina', 'siren': 'sirene', 'clock_alarm': 'alarme'}
ESC_SKIP = {'church_bells'}  # sinos: parecidos com campainha, fora do ambiente
for r in csv.DictReader(open('/home/claude/src/esc50/meta/esc50.csv')):
    if r['category'] in ESC_SKIP:
        continue
    c = ESC_MAP.get(r['category'], 'ambiente')
    add(c, '/home/claude/cache/esc50/' + r['filename'], 'ESC-50', 'esc:' + r['src_file'], 'CC BY-NC 3.0',
        {'esc_cat': r['category']})

# ---- Campainhas reais no GitHub --------------------------------------------------
for f in ['doorbell_detector__raw_data_bel.wav', 'doorbell_detector__raw_data_bel2.wav']:
    add('campainha', '/home/claude/cache/doorbell/' + f, 'thepycoder/doorbell_detector', 'pyc:' + f, 'sem licença declarada (repo público)')
for f in ['unifi-g4-doorbell-sounds__sounds_sounds_ring_button_Chime.wav', 'unifi-g4-doorbell-sounds__sounds_sounds_ring_button_Ding-dong.wav']:
    add('campainha', '/home/claude/cache/doorbell/' + f, 'johnzanussi/unifi-g4-doorbell-sounds', 'unifi:' + f, 'sem licença declarada (repo público)')

# ---- Ambiente ---------------------------------------------------------------------
for p in sorted(glob.glob('/home/claude/raw/speech/*.wav')):
    rd = re.search(r'reader_(\d+)_', p).group(1)
    add('ambiente', p, 'LibriVox (via DNS Challenge 2020)', 'spk:' + rd, 'domínio público', {'amb_tipo': 'fala'})
for split in ['noise_train', 'noise_test']:
    for p in sorted(glob.glob(f'/home/claude/src/mssnsd/{split}/*.wav')):
        add('ambiente', p, 'MS-SNSD (Microsoft)', 'snsd:' + split + '/' + os.path.basename(p), 'CC0 (Freesound) / CC BY-SA 3.0 (DEMAND)',
            {'force_split': 'train' if split == 'noise_train' else 'test', 'amb_tipo': 'ruido'})
for p in sorted(glob.glob('/home/claude/cache/pycoder_amb/*.wav')):
    add('ambiente', p, 'thepycoder/doorbell_detector (ambiente doméstico)', 'pycamb:' + os.path.basename(p)[:7], 'sem licença declarada (repo público)',
        {'amb_tipo': 'casa'})

for it in items:
    it['dur'] = round(sf.info(it['path']).duration, 2)

json.dump(items, open(W + 'inventario.json', 'w'), ensure_ascii=False)
cnt = collections.Counter((i['cls'], i['dataset']) for i in items)
for k, v in sorted(cnt.items()):
    print(v, k)
# lista para o etiquetador: todas as fontes (alvo + ambiente)
open(W + 'tag_list.txt', 'w').write('\n'.join(i['path'] for i in items) + '\n')
print('total', len(items))
