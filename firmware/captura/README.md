# firmware/captura

Sketch usado **apenas para gravar dataset**, não para inferência. O arquivo
principal é o `captura.ino` (mesmo nome da pasta, como o Arduino exige).

Lê o áudio cru do microfone (via I2S / ES7210) e envia as amostras
pela porta serial em **formato binário** (2 bytes por amostra,
int16 little-endian) usando `Serial.write()`.

## Requisitos para funcionar

- Baud rate no `Serial.begin()` deve ser **exatamente igual** ao
  `BAUD_RATE` definido em `tools/captura_audio.py`. Atualmente: `921600`.
- O script Python correspondente (`tools/captura_audio.py`) precisa
  estar na versão que lê **bytes brutos** (`ser.read()`), não na
  versão antiga que lia linha de texto (`ser.readline()`). O
  formato texto não cabe na banda da serial em 16kHz e causa perda
  de amostras, distorcendo o timing/pitch do áudio capturado.
- Depois de gravar o dataset, sobe o sketch de `firmware/inferencia`
  de volta antes de testar o dispositivo em uso normal — este
  sketch não roda o classificador.

## Uso

1. Sobe este sketch no ESP32.
2. Roda `python captura_audio.py <PORTA_COM> <NOME_DA_CLASSE> [duracao_segundos]`
   no computador conectado.
3. Produz o som real perto do microfone durante a contagem
   regressiva / gravação.

## Conferido no CI

A cada push que mexe em `firmware/`, o GitHub Actions compila este sketch para o
ESP32-S3 (`.github/workflows/firmware.yml`). Os testes de contrato
(`tests/test_contratos_firmware.py`) conferem que o baud rate daqui é igual ao
`BAUD_RATE` do script Python e que o `gainVal` é igual ao do sketch de inferência.
