# Como contribuir

## Fluxo

1. Crie uma branch a partir da `main`, com prefixo pelo tipo de mudança:
   - `feat/` para funcionalidade;
   - `fix/` para correção;
   - `dados/` para dataset;
   - `docs/` para documentação;
   - `ci/` para o pipeline.
2. Faça commits pequenos e com uma intenção só.
3. Abra um pull request para a `main`. O GitHub Actions roda o pipeline e o merge só acontece com tudo verde.

## Mensagens de commit

Use o padrão `tipo(escopo): descrição no imperativo`, em português:

```
feat(firmware): adiciona padrão háptico para sirene
fix(ml): corrige nível do piso de ruído com PGA diferente de 24 dB
dados: adiciona sessão de validação gravada na rua
ci: valida o dataset a cada mudança em datasets/
```

Tipos usados: `feat`, `fix`, `dados`, `ml`, `test`, `ci`, `docs`, `refactor`, `style`, `hardware`.

## Antes de abrir o pull request

```bash
pip install -r requirements-dev.txt
ruff check ml tests tools && ruff format --check ml tests tools
pytest
python ml/validar_dataset.py datasets   # se mexeu em datasets/
```

## Regras que o CI garante

- **Código Python**: precisa passar no `ruff check` e no `ruff format --check`.
- **Testes**: todos os testes de `tests/` precisam passar.
- **Valores compartilhados**: baud rate, taxa de amostragem e ganho do microfone (`gainVal`) têm que ser iguais no firmware de captura, no de inferência e no `tools/captura_audio.py`.
- **Dataset**:
  - todo WAV em `datasets/` precisa estar no `info.labels`, ser 16 kHz mono PCM16 e ter o nome começando pelo rótulo;
  - nenhuma gravação (metadado `gravacao`) pode estar em treino e teste ao mesmo tempo;
  - não use o "Perform train/test split" do Edge Impulse.
- **Firmware**: o sketch de captura precisa compilar para `esp32:esp32:esp32s3`.

## Dados novos gravados no relógio

1. Grave com `firmware/captura` + `tools/captura_audio.py`.
2. Coloque os WAVs em `datasets/relogio/treino` (ou `teste`, se for uma sessão de validação nova).
3. Acrescente as entradas no `datasets/info.labels`, com `gravacao` e `sessao`.
4. Rode o validador antes do push.
