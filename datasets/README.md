# Datasets

Esta pasta já está no formato de upload do Edge Impulse: um `info.labels` único na raiz diz, pra cada WAV, o rótulo, se ele vai pra treino ou teste e os metadados.

| pasta | o que é | amostras |
|---|---|---:|
| `relogio/` | gravações reais feitas pelo microfone do relógio (sessões perto, longe, media, mídia, tv, sons-casa, silêncio e validação) | 1.240 |
| `publico_simulado_v3/` | áudio público com a cadeia de captação do relógio simulada e calibrada (janelas de 1 s) | 60.801 |

## Divisão treino/teste

- **Teste:** só a sessão `validacao` do relógio, 50 gravações reais que o modelo nunca vê no treino. É o número que vale pro relógio.
- **Treino:** todo o resto, 61.991 amostras.
- **Vazamento:** nenhuma gravação de origem (metadado `gravacao`) aparece nos dois lados, e o CI confere isso a cada push.

| classe | treino | teste |
|---|---:|---:|
| alarme | 11.846 | 11 |
| ambiente | 16.135 | 10 |
| buzina | 10.207 | 8 |
| campainha | 11.957 | 10 |
| sirene | 11.846 | 11 |

## Como subir no Edge Impulse

1. Apague os dados antigos do projeto, nas abas Training e Test.
2. Vá em Data acquisition > Add data > Upload data e escolha esta pasta `datasets` inteira.
3. No Classifier, use "Split train/validation set on metadata key: gravacao" e deixe "Auto-weight classes" ligado. Com esse volume de dados, uns 30 ciclos de treino bastam.
4. Nunca use o "Perform train/test split": ele embaralha janela por janela e traz de volta o vazamento.
5. No deploy, use Unoptimized (float32).

Pelo terminal: `edge-impulse-uploader --info-file info.labels --api-key ei_...` de dentro desta pasta.

## Metadados

Toda amostra tem:

- `gravacao`: a gravação ou fonte de origem;
- `sessao`;
- `origem`: `relogio`, `real` (áudio público gravado de verdade) ou `sintetico`.

As do dataset público também têm dataset, fonte, tipo, ambiente acústico, alto-falante, SPL, SNR e PGA. O `publico_simulado_v3/manifesto.csv` detalha cada arquivo, inclusive a licença.

## Fontes e licenças do dataset público

- AudioSet (CC BY 4.0), via o conjunto de ruídos do DNS Challenge 2020 da Microsoft.
- ESC-50 (CC BY-NC 3.0).
- LibriVox (domínio público).
- MS-SNSD (CC0 e CC BY-SA 3.0).
- Os repositórios públicos thepycoder/doorbell_detector e johnzanussi/unifi-g4-doorbell-sounds.
- Síntese física própria.

Da campainha, 97% das amostras são sintéticas, porque quase não existem gravações reais acessíveis. Detalhes da calibração do microfone em `ml/README.md`.
