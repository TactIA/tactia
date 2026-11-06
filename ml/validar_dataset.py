"""Valida uma pasta de dataset no formato do Edge Impulse (info.labels + WAVs).

Roda no CI a cada mudança em datasets/ e pode ser usado localmente:

    python ml/validar_dataset.py datasets
    python ml/validar_dataset.py datasets --resumo resumo.md

Checagens (qualquer erro faz o script sair com código 1):
  - info.labels é um JSON válido com a lista "files";
  - cada entrada aponta para um arquivo que existe, com categoria training/testing e rótulo conhecido;
  - o nome do arquivo começa pelo rótulo (o Edge Impulse usa isso quando o upload é feito sem info.labels);
  - todo WAV é 16 kHz, mono, PCM 16 bit e tem pelo menos 1 s;
  - não há WAV na pasta que tenha ficado fora do info.labels, nem caminho repetido;
  - nenhuma gravação de origem (metadado "gravacao") aparece em treino e teste ao mesmo tempo,
    que é o vazamento que inflou os resultados de versões antigas do modelo.
"""

import argparse
import collections
import json
import os
import sys

import soundfile as sf

CLASSES = {"alarme", "ambiente", "buzina", "campainha", "sirene"}
CATEGORIAS = {"training", "testing"}
TAXA = 16000


def validar(pasta, checar_audio=True):
    erros = []
    avisos = []
    caminho_info = os.path.join(pasta, "info.labels")
    if not os.path.exists(caminho_info):
        return ["info.labels não encontrado em " + pasta], avisos, {}
    try:
        info = json.load(open(caminho_info, encoding="utf-8"))
        arquivos = info["files"]
    except (json.JSONDecodeError, KeyError) as e:
        return [f"info.labels inválido: {e}"], avisos, {}

    vistos = set()
    gravacao_cat = collections.defaultdict(set)
    contagem = collections.Counter()
    origem = collections.Counter()
    for i, f in enumerate(arquivos):
        p = f.get("path", "")
        cat = f.get("category")
        rot = (f.get("label") or {}).get("label")
        md = f.get("metadata") or {}
        if p in vistos:
            erros.append(f"caminho repetido: {p}")
        vistos.add(p)
        if cat not in CATEGORIAS:
            erros.append(f"{p}: categoria inválida {cat!r}")
        if rot not in CLASSES:
            erros.append(f"{p}: rótulo desconhecido {rot!r}")
            continue
        if not os.path.basename(p).startswith(rot + "."):
            erros.append(f"{p}: nome do arquivo não começa com o rótulo '{rot}.'")
        completo = os.path.join(pasta, p)
        if not os.path.exists(completo):
            erros.append(f"{p}: arquivo não existe")
            continue
        if checar_audio:
            try:
                a = sf.info(completo)
            except RuntimeError as e:
                erros.append(f"{p}: WAV ilegível ({e})")
                continue
            if a.samplerate != TAXA or a.channels != 1 or a.subtype != "PCM_16":
                erros.append(f"{p}: formato {a.samplerate} Hz / {a.channels} canal(is) / {a.subtype}")
            if a.frames < TAXA:
                erros.append(f"{p}: menor que 1 s ({a.frames} amostras)")
        if md.get("gravacao"):
            gravacao_cat[md["gravacao"]].add(cat)
        contagem[(cat, rot)] += 1
        origem[(cat, md.get("origem", "?"))] += 1

    for g, cats in gravacao_cat.items():
        if len(cats) > 1:
            erros.append(f"vazamento: a gravação '{g}' está em treino e em teste")

    no_disco = set()
    for raiz, _, nomes in os.walk(pasta):
        for n in nomes:
            if n.lower().endswith(".wav"):
                no_disco.add(os.path.relpath(os.path.join(raiz, n), pasta))
    fora = sorted(no_disco - vistos)
    for p in fora[:20]:
        erros.append(f"{p}: WAV fora do info.labels (não seria enviado ao Edge Impulse)")
    if len(fora) > 20:
        erros.append(f"... e mais {len(fora) - 20} WAVs fora do info.labels")

    if not any(c == "testing" for c, _ in contagem):
        avisos.append("nenhuma amostra de teste")
    resumo = {"total": len(arquivos), "contagem": contagem, "origem": origem}
    return erros, avisos, resumo


def tabela_markdown(resumo):
    linhas = ["| classe | treino | teste |", "|---|---:|---:|"]
    c = resumo["contagem"]
    for rot in sorted(CLASSES):
        linhas.append(f"| {rot} | {c[('training', rot)]:,} | {c[('testing', rot)]:,} |".replace(",", "."))
    tt = sum(v for (cat, _), v in c.items() if cat == "training")
    te = sum(v for (cat, _), v in c.items() if cat == "testing")
    linhas.append(f"| **total** | **{tt:,}** | **{te:,}** |".replace(",", "."))
    linhas.append("")
    linhas.append("| origem | treino | teste |")
    linhas.append("|---|---:|---:|")
    o = resumo["origem"]
    for org in sorted({k for _, k in o}):
        linhas.append(f"| {org} | {o[('training', org)]:,} | {o[('testing', org)]:,} |".replace(",", "."))
    return "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pasta")
    ap.add_argument("--resumo", help="acrescenta um resumo em Markdown neste arquivo (ex.: $GITHUB_STEP_SUMMARY)")
    ap.add_argument("--sem-audio", action="store_true", help="não abre os WAVs (só info.labels e caminhos)")
    a = ap.parse_args()
    erros, avisos, resumo = validar(a.pasta, checar_audio=not a.sem_audio)
    for w in avisos:
        print("AVISO:", w)
    for e in erros[:200]:
        print("ERRO:", e)
    if resumo:
        print(tabela_markdown(resumo))
    if a.resumo:
        with open(a.resumo, "a", encoding="utf-8") as f:
            f.write("## Validação do dataset\n\n")
            f.write(("✅ Nenhum erro" if not erros else f"❌ {len(erros)} erro(s)") + "\n\n")
            if resumo:
                f.write(tabela_markdown(resumo) + "\n")
    print(f"\n{resumo.get('total', 0)} amostras, {len(erros)} erro(s), {len(avisos)} aviso(s)")
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    main()
