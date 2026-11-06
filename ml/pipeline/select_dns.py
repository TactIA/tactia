from config import SRC
import json
import random
import collections
import csv

random.seed(7)
names = {r["id"]: r["label"] for r in csv.DictReader(open(SRC + "asmeta/class_labels.tsv"), delimiter="\t")}
lab = json.load(open("dns_labels.json"))
G = {
    "sirene": ["/m/03kmc9", "/m/04qvtq", "/m/012n7d", "/m/012ndj", "/m/0dgbq", "/m/03j1ly"],
    "buzina": ["/m/0912c9", "/m/05x_td", "/m/07qv_d5"],
    "alarme": ["/m/07pp_mv", "/m/046dlr", "/m/01y3hg", "/m/0c3f7m", "/m/02mfyn"],
    "campainha": ["/m/03wwcy", "/m/07r67yg", "/m/07phxs1"],
}
# labels that make a clip unsuitable for "ambiente" (alert-like or too similar to targets)
EXCL = set(sum(G.values(), [])) | {
    "/m/030rvx",
    "/m/02fs_r",
    "/m/01hnzm",
    "/m/07pp8cl",
    "/m/07cx4",
    "/m/02rhddq",
    "/m/0f8s22",
    "/m/0395lw",
    "/m/03w41f",
    "/m/026fgl",
    "/m/07qcpgn",
    "/m/027m70_",
    "/m/016622",
    "/m/0gy1t2s",
    "/m/0284vy3",
    "/m/04fq5q",
    "/m/0l156k",
    "/g/11b630rrvh",
    "/m/06hck5",
    "/m/04zmvq",
    "/m/06cyt0",
    "/m/0239kh",
    "/m/0ytgt",
}
for k in list(names):
    if any(
        w in names[k].lower()
        for w in [
            "glockenspiel",
            "marimba",
            "mallet",
            "steelpan",
            "vibraphone",
            "chime",
            "bell",
            "horn",
            "siren",
            "alarm",
            "beep",
            "buzzer",
            "ringtone",
            "whistle",
        ]
    ):
        EXCL.add(k)
sel = {}
for y, ls in lab.items():
    s = set(ls)
    hit = [c for c, ids in G.items() if s & set(ids)]
    if len(hit) == 1:
        sel[y] = hit[0]
    elif len(hit) > 1:
        pass  # ambiguous, skip
amb = [y for y, ls in lab.items() if not (set(ls) & EXCL)]
# stratify ambiente by first label to keep diversity
by = collections.defaultdict(list)
for y in amb:
    by[tuple(sorted(lab[y]))[0]].append(y)
random.shuffle(amb)
# round-robin over label groups
pick = []
keys = list(by)
[random.shuffle(by[k]) for k in keys]
while len(pick) < 4200:
    for k in keys:
        if by[k]:
            pick.append(by[k].pop())
for y in pick[:4200]:
    sel[y] = "ambiente"
print(collections.Counter(sel.values()))
json.dump(sel, open("dns_selected.json", "w"))
open("dns_download.txt", "w").write("\n".join(sel) + "\n")
