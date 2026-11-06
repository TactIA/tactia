# ml — simulador do microfone e geração do dataset

Aqui fica o código que gerou o dataset público com o microfone do relógio simulado (`datasets/publico_simulado_v3`).

O problema que ele resolve: só dá pra gravar uns poucos sons pelo relógio, e um modelo treinado com áudio público "cru" confundia tudo no aparelho. A saída foi pegar áudio público e passar cada amostra pela mesma cadeia de captação do relógio, calibrada com gravações reais dele.

## Módulos principais

- `tactia_mic.py`: a cadeia de captação, de pressão sonora (Pa) até amostras int16 a 16 kHz. Ela simula:
  - sala ou ambiente externo;
  - nível em dB SPL;
  - sombra do pulso;
  - par de microfones;
  - MEMS (passa-altas, ressonância da porta acústica, saturação);
  - ES7210 (ganho, filtro de decimação, passa-altas digital, quantização);
  - piso de ruído medido no relógio, com o zumbido de ~54 Hz e os tons de 6 e 7 kHz.
- `perfil_mic_relogio.json`: o perfil medido nas 15 gravações de silêncio do relógio.
- `tactia_synth.py`: sintetizadores por modelo físico:
  - campainha: ding-dong de barras, eletrônica com melodias, cigarra, sino e dois tons;
  - alarme: detector de fumaça T3/T4, despertadores e alarme de incêndio;
  - buzina;
  - sirene eletrônica;
  - motor de vibração do próprio relógio.
- `validar_dataset.py`: o validador que roda no CI. Confere rótulos, formato dos WAVs e vazamento entre treino e teste.

## Pipeline (`pipeline/`)

Os scripts rodam nesta ordem. Os caminhos ficam em `pipeline/config.py`, com a pasta de trabalho padrão `ml/_trabalho`, que é ignorada pelo git:

1. `map_dns.py` e `select_dns.py` cruzam os ~55 mil clipes de ruído do DNS Challenge 2020 com os rótulos oficiais do AudioSet e escolhem os clipes de cada classe.
2. `prep.py` converte ESC-50, campainhas e o ambiente doméstico para 16 kHz mono.
3. `inventario.py` monta o inventário de fontes, com o grupo de origem (vídeo, gravação, locutor) e a licença de cada uma.
4. `janelas_validas.py`, com `heur.py`, encontra as janelas de 1 s em que o evento aparece. Usa o rótulo temporal do AudioSet quando existe e, quando não, uma heurística de energia e tonalidade.
5. `calibrar_microfone.py` gera o `perfil_mic_relogio.json` a partir de gravações de silêncio do relógio.
6. `gerar_dataset.py` gera as janelas. O split treino/teste é feito por grupo de origem, e os sons de fundo também respeitam o split.
7. `finalizar.py` gera o `info.labels`, o manifesto e confere o vazamento.
8. `checar_aprendizado.py` e `transfer_eval.py` treinam um MLP de referência e medem o acerto nas gravações reais do relógio, que foi o critério usado pra escolher cada ajuste.

Instalação: `pip install -r ml/requirements.txt`. As fontes vêm de repositórios públicos no GitHub: ESC-50, MS-SNSD, os metadados do AudioSet reformatados (bakhtos/GoogleAudioSetReformatted) e os áudios do microsoft/DNS-Challenge (branch `interspeech2020/master`).
