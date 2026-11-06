# Changelog

Mudanças relevantes do TactIA, da mais recente para a mais antiga. As datas são as de quando cada parte foi feita.

## [2.0.0] — 2026-11-06

### Adicionado
- Integração contínua no GitHub Actions: lint (ruff), 72 testes (pytest), validação do dataset e compilação do firmware.
- `ml/`:
  - simulador da cadeia de captação do relógio (MEMS + ES7210), calibrado com gravações reais de silêncio;
  - sintetizadores físicos;
  - pipeline de geração do dataset;
  - validador de dataset.
- `datasets/publico_simulado_v3`: 60.801 janelas de 1 s de áudio público passadas pelo microfone simulado, com split por gravação de origem.
- `datasets/info.labels` único (relógio + v3), pronto para o upload no Edge Impulse; o teste é só a sessão `validacao` do relógio.
- Testes de contrato entre firmware e script de captura (baud rate, taxa de amostragem e ganho).
- `pin_config.h` da Waveshare junto dos sketches.
- Modelo 3D da carcaça (`hardware/carcaca`), artigo do EnGeTec 2026 e figuras (`docs/`).
- README de apresentação, guia de contribuição e templates de issue e pull request.

### Alterado
- Sketches renomeados para `captura.ino` e `inferencia.ino` (o Arduino exige o mesmo nome da pasta).
- `tools/captura_audio.py` formatado com ruff, sem mudança de comportamento.

## [1.1.0] — 2026-11-01

### Adicionado
- Gravações reais do relógio limpas e organizadas por sessão (perto, longe, media, mídia, tv, sons-casa, silêncio e validação), com a lista do que foi removido ou movido na limpeza.

## [1.0.0] — 2026-09-18

### Adicionado
- Firmware de inferência com o modelo do Edge Impulse:
  - normalização;
  - votação por janela;
  - limiares por classe;
  - média dos dois canais do microfone.

### Corrigido
- Remoção da dependência Adafruit_DRV2605: padrões hápticos via GPIO.
- Motor de vibração desativado enquanto o hardware não está conectado (alerta pela Serial).

## [0.1.0] — 2026-08-27

### Adicionado
- Estrutura inicial do projeto: sketch de captura, script `captura_audio.py` e README.
