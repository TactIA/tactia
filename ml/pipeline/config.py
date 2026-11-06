"""Caminhos do pipeline de geração do dataset.

Tudo fica dentro de TACTIA_TRABALHO (padrão: ml/_trabalho, ignorado pelo git):
  src/    repositórios clonados (ESC-50, MS-SNSD, metadados do AudioSet, DNS Challenge)
  raw/    áudios baixados (ruídos/fala do DNS Challenge, campainhas)
  cache/  fontes convertidas para 16 kHz mono
  work/   listas, inventário, etiquetas e features intermediárias
"""

import os
import sys
from pathlib import Path

_ML = Path(__file__).resolve().parents[1]
# permite "import tactia_mic" / "import tactia_synth" a partir de ml/pipeline
if str(_ML) not in sys.path:
    sys.path.insert(0, str(_ML))
RAIZ = Path(os.environ.get("TACTIA_TRABALHO", _ML / "_trabalho"))
SRC = str(RAIZ / "src") + "/"
RAW = str(RAIZ / "raw") + "/"
CACHE = str(RAIZ / "cache") + "/"
WORK = str(RAIZ / "work") + "/"
DATASET_RELOGIO = os.environ.get("TACTIA_DATASET_RELOGIO", str(_ML.parent / "datasets" / "relogio") + "/")
