from config import SRC, WORK
import csv
import collections
import re
import json

base = SRC + "asmeta/"
names = {}
for r in csv.DictReader(open(base + "class_labels.tsv"), delimiter="\t"):
    names[r["id"]] = r["label"]
labels = collections.defaultdict(set)
seg = {}
for f in [
    "audioset_weak_eval.tsv",
    "audioset_weak_train_balanced.tsv",
    "audioset_weak_train_unbalanced.tsv",
    "audioset_weak_train_unbalanced2.tsv",
]:
    for r in csv.DictReader(open(base + f), delimiter="\t"):
        fn = r["filename"]
        yt = fn[:11]
        labels[yt].add(r["event_label"])
        seg[yt] = fn
strong = collections.defaultdict(list)
for f in ["audioset_strong_train.tsv", "audioset_strong_eval.tsv"]:
    for r in csv.DictReader(open(base + f), delimiter="\t"):
        strong[r["filename"][:11]].append((r["event_label"], float(r["onset"]), float(r["offset"])))
files = [linha.strip() for linha in open(WORK + "dns_noise_files.txt")]
yt = [f[:-4] for f in files if re.fullmatch(r".{11}\.wav", f)]
print(
    "youtube clips",
    len(yt),
    "with labels",
    sum(1 for y in yt if y in labels),
    "with strong",
    sum(1 for y in yt if y in strong),
)
cnt = collections.Counter()
for y in yt:
    for lab in labels.get(y, ()):
        cnt[lab] += 1
for lab, c in cnt.most_common(200):
    print(c, names.get(lab, lab))
json.dump({y: sorted(labels[y]) for y in yt if y in labels}, open(WORK + "dns_labels.json", "w"))
json.dump({y: strong[y] for y in yt if y in strong}, open(WORK + "dns_strong.json", "w"))
json.dump({y: seg[y] for y in yt if y in seg}, open(WORK + "dns_seg.json", "w"))
