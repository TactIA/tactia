"""
TactIA — Captura de áudio via Serial para arquivo .wav
=======================================================
Lê as amostras que o relógio envia pelo Serial em formato BINÁRIO
(2 bytes por amostra, int16 little-endian) e salva como um arquivo
.wav pronto para subir manualmente no Edge Impulse Studio.

IMPORTANTE: este script espera que o firmware do ESP32 envie as
amostras com Serial.write() em binário, não mais com Serial.println()
em texto. O formato texto (uma linha por amostra) não cabe na banda
da porta serial em 16kHz e causa perda de amostras — o que distorce
o timing/pitch do áudio capturado. No sketch do Arduino, troque:

    Serial.println(valor);          // ANTES (texto, lento)

por:

    int16_t v = valor;
    Serial.write((uint8_t*)&v, 2);  // AGORA (binário, 2 bytes fixos)

Requisitos:
    pip install pyserial

Uso:
    python captura_audio.py <PORTA_COM> <NOME_DA_CLASSE> [duracao_segundos]

Exemplos:
    python captura_audio.py COM3 buzina
    python captura_audio.py COM3 campainha 5

Cada execução gera um arquivo numerado automaticamente, por exemplo:
    dataset/buzina.1.wav
    dataset/buzina.2.wav
    dataset/campainha.1.wav

Rode o script várias vezes por classe, com o som acontecendo de
verdade perto do microfone durante a gravação. A contagem regressiva
dá tempo de posicionar/disparar o som antes da captura começar.
"""

import sys
import os
import wave
import time
import glob
import serial

SAMPLE_RATE = 16000
BAUD_RATE = 921600
OUTPUT_DIR = "dataset"
BYTES_POR_AMOSTRA = 2  # int16


def proxima_numeracao(label):
    padrao = os.path.join(OUTPUT_DIR, f"{label}.*.wav")
    existentes = glob.glob(padrao)
    numeros = []
    for caminho in existentes:
        nome = os.path.basename(caminho)
        partes = nome.split(".")
        if len(partes) >= 3 and partes[-2].isdigit():
            numeros.append(int(partes[-2]))
    return max(numeros, default=0) + 1


def contagem_regressiva(segundos=3):
    for i in range(segundos, 0, -1):
        print(f"Gravando em {i}...")
        time.sleep(1)


def main():
    if len(sys.argv) < 3:
        print("Uso: python captura_audio.py <PORTA_COM> <NOME_DA_CLASSE> [duracao_segundos]")
        print("Exemplo: python captura_audio.py COM3 buzina 3")
        sys.exit(1)

    porta = sys.argv[1]
    label = sys.argv[2]
    duracao = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    numero = proxima_numeracao(label)
    caminho_saida = os.path.join(OUTPUT_DIR, f"{label}.{numero}.wav")

    print(f"Conectando na porta {porta}...")
    ser = serial.Serial(porta, BAUD_RATE, timeout=1)
    time.sleep(2)  # espera o ESP32 estabilizar a conexão serial
    ser.reset_input_buffer()

    contagem_regressiva(3)
    print(f"GRAVANDO '{label}' agora — produza o som perto do microfone!")

    total_esperado = int(SAMPLE_RATE * duracao)
    bytes_esperados = total_esperado * BYTES_POR_AMOSTRA
    dados = bytearray()
    inicio = time.time()

    while len(dados) < bytes_esperados and (time.time() - inicio) < (duracao + 5):
        faltam = bytes_esperados - len(dados)
        chunk = ser.read(faltam)  # lê bytes brutos, bloqueia até timeout ou encher
        dados.extend(chunk)

    ser.close()

    amostras_recebidas = len(dados) // BYTES_POR_AMOSTRA
    tempo_real = time.time() - inicio

    if amostras_recebidas < SAMPLE_RATE * 0.5:
        print(f"Aviso: só {amostras_recebidas} amostras capturadas — confira se o sketch de captura está rodando e a porta está certa.")

    diferenca_pct = abs(amostras_recebidas - total_esperado) / total_esperado * 100
    print(f"Recebido: {amostras_recebidas} amostras em {tempo_real:.2f}s de relógio "
          f"(esperado: {total_esperado} amostras / {duracao:.2f}s)")
    if diferenca_pct > 2:
        print(f"⚠️  Diferença de {diferenca_pct:.1f}% entre esperado e recebido — "
              f"ainda pode haver perda de dados na serial. Considere refazer esta gravação.")
    else:
        print("✅ Contagem de amostras bateu com o esperado — captura íntegra.")

    # Descarta bytes sobrando (caso tenha lido 1 byte a mais de um sample incompleto)
    dados = dados[: amostras_recebidas * BYTES_POR_AMOSTRA]

    with wave.open(caminho_saida, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16 bits
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframesraw(bytes(dados))

    print(f"Salvo: {caminho_saida} ({amostras_recebidas} amostras, ~{amostras_recebidas/SAMPLE_RATE:.1f}s)")


if __name__ == "__main__":
    main()