"""
TactIA — Captura de áudio via Serial para arquivo .wav
=======================================================
Lê as amostras que o relógio envia pelo Serial em formato BINÁRIO
(2 bytes por amostra, int16 little-endian) e salva como um arquivo
.wav pronto para subir manualmente no Edge Impulse Studio.

O firmware do ESP32 já envia a MÉDIA dos dois canais (L+R)/2 como
int16 — exatamente o mesmo processamento do firmware de inferência,
garantindo consistência entre dataset e produção.

Requisitos:
    pip install pyserial numpy

Uso:
    python captura_audio.py <PORTA_COM> <NOME_DA_CLASSE> [duracao_segundos]

Exemplos:
    python captura_audio.py COM3 buzina
    python captura_audio.py COM3 campainha 5
    python captura_audio.py /dev/ttyUSB0 sirene 4

Cada execução gera um arquivo numerado automaticamente, por exemplo:
    dataset/buzina.1.wav
    dataset/buzina.2.wav
    dataset/campainha.1.wav

A gravação é validada automaticamente:
  - Se a contagem de amostras divergir > 2% do esperado → aviso de perda
  - Se o RMS do áudio for muito baixo → aviso de gravação silenciosa
  - Gravações inválidas recebem sufixo _INVALIDA e não são descartadas,
    mas você deve regravá-las antes de subir ao Edge Impulse.

Rode o script várias vezes por classe, com o som acontecendo de
verdade perto do microfone durante a contagem regressiva.
"""

import sys
import os
import wave
import time
import glob
import struct
import serial

# numpy é opcional — usado apenas para cálculo de RMS
try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    _NUMPY_OK = False

SAMPLE_RATE      = 16000
BAUD_RATE        = 921600
OUTPUT_DIR       = "dataset"
BYTES_POR_AMOSTRA = 2  # int16

# Limiar de RMS abaixo do qual a gravação é considerada "silenciosa".
# Em escala int16: 200 ≈ -44 dBFS. Sons reais ficam acima de 500–2000.
RMS_THRESHOLD = 200

# Limiar de pico: se o pico absoluto for muito baixo o microfone pode
# estar desconectado ou o sketch de captura não estar rodando.
PICO_THRESHOLD = 500


def calcular_rms(dados: bytes) -> float:
    """Retorna o RMS do áudio em escala int16 (0–32768)."""
    n = len(dados) // BYTES_POR_AMOSTRA
    if n == 0:
        return 0.0
    if _NUMPY_OK:
        samples = np.frombuffer(dados, dtype="<i2").astype(np.float64)
        return float(np.sqrt(np.mean(samples ** 2)))
    else:
        soma_quad = 0
        for i in range(n):
            v = struct.unpack_from("<h", dados, i * 2)[0]
            soma_quad += v * v
        return (soma_quad / n) ** 0.5


def calcular_pico(dados: bytes) -> int:
    """Retorna o pico absoluto do áudio em escala int16."""
    n = len(dados) // BYTES_POR_AMOSTRA
    if n == 0:
        return 0
    if _NUMPY_OK:
        samples = np.frombuffer(dados, dtype="<i2")
        return int(np.max(np.abs(samples)))
    else:
        pico = 0
        for i in range(n):
            v = abs(struct.unpack_from("<h", dados, i * 2)[0])
            if v > pico:
                pico = v
        return pico


def proxima_numeracao(label: str) -> int:
    padrao = os.path.join(OUTPUT_DIR, f"{label}.*.wav")
    existentes = glob.glob(padrao)
    numeros = []
    for caminho in existentes:
        nome = os.path.basename(caminho)
        partes = nome.split(".")
        if len(partes) >= 3 and partes[-2].isdigit():
            numeros.append(int(partes[-2]))
    return max(numeros, default=0) + 1


def contagem_regressiva(segundos: int = 3) -> None:
    for i in range(segundos, 0, -1):
        print(f"  Gravando em {i}...")
        time.sleep(1)


def validar_gravacao(dados: bytes, duracao: float) -> list[str]:
    """
    Retorna lista de avisos encontrados na gravação.
    Lista vazia = gravação íntegra.
    """
    avisos = []
    amostras = len(dados) // BYTES_POR_AMOSTRA
    total_esperado = int(SAMPLE_RATE * duracao)

    # 1. Verificação de contagem de amostras
    if amostras < SAMPLE_RATE * 0.5:
        avisos.append(
            f"Muito poucas amostras ({amostras}) — confira se o sketch de captura "
            f"está rodando e a porta está correta."
        )
    else:
        diferenca_pct = abs(amostras - total_esperado) / total_esperado * 100
        if diferenca_pct > 2:
            avisos.append(
                f"Perda de dados: {diferenca_pct:.1f}% de diferença entre "
                f"esperado ({total_esperado}) e recebido ({amostras}) — refaça esta gravação."
            )

    # 2. Verificação de amplitude (RMS)
    rms = calcular_rms(dados)
    if rms < RMS_THRESHOLD:
        avisos.append(
            f"RMS muito baixo ({rms:.0f}) — áudio silencioso. "
            f"Produza o som bem perto do microfone e refaça."
        )

    # 3. Verificação de pico absoluto
    pico = calcular_pico(dados)
    if pico < PICO_THRESHOLD:
        avisos.append(
            f"Pico absoluto muito baixo ({pico}) — microfone pode estar "
            f"desconectado ou o sketch errado está carregado."
        )

    return avisos


def salvar_wav(caminho: str, dados: bytes) -> None:
    amostras = len(dados) // BYTES_POR_AMOSTRA
    with wave.open(caminho, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)           # 16 bits
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframesraw(dados)
    print(f"Salvo: {caminho} ({amostras} amostras, ~{amostras / SAMPLE_RATE:.1f}s)")


def main() -> None:
    if len(sys.argv) < 3:
        print("Uso:    python captura_audio.py <PORTA_COM> <NOME_DA_CLASSE> [duracao_segundos]")
        print("Exemplo: python captura_audio.py COM3 buzina 3")
        sys.exit(1)

    if not _NUMPY_OK:
        print("⚠️  numpy não encontrado — validação de RMS usa fallback puro-Python (mais lento).")
        print("   Instale com: pip install numpy")

    porta  = sys.argv[1]
    label  = sys.argv[2]
    duracao = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    numero         = proxima_numeracao(label)
    caminho_saida  = os.path.join(OUTPUT_DIR, f"{label}.{numero}.wav")

    print(f"\nConectando na porta {porta} a {BAUD_RATE} baud...")
    ser = serial.Serial(porta, BAUD_RATE, timeout=1)
    time.sleep(2)          # aguarda o ESP32 estabilizar
    ser.reset_input_buffer()

    print(f"\nClasse: '{label}' | Duração: {duracao:.1f}s | Arquivo: {caminho_saida}")
    contagem_regressiva(3)
    print(f"🎙️  GRAVANDO agora — produza o som perto do microfone!\n")

    total_esperado  = int(SAMPLE_RATE * duracao)
    bytes_esperados = total_esperado * BYTES_POR_AMOSTRA
    dados           = bytearray()
    inicio          = time.time()

    while len(dados) < bytes_esperados and (time.time() - inicio) < (duracao + 5):
        faltam = bytes_esperados - len(dados)
        chunk  = ser.read(faltam)
        dados.extend(chunk)

    ser.close()

    amostras_recebidas = len(dados) // BYTES_POR_AMOSTRA
    tempo_real         = time.time() - inicio
    print(f"Recebido: {amostras_recebidas} amostras em {tempo_real:.2f}s "
          f"(esperado: {total_esperado} amostras / {duracao:.1f}s)")

    # Descarta bytes incompletos (último int16 parcial)
    dados = dados[: amostras_recebidas * BYTES_POR_AMOSTRA]

    # --- Validação da gravação ---
    avisos = validar_gravacao(bytes(dados), duracao)

    if not avisos:
        print("✅ Gravação íntegra — contagem, RMS e pico dentro do esperado.")
        salvar_wav(caminho_saida, bytes(dados))
    else:
        print("\n⚠️  Problemas encontrados na gravação:")
        for aviso in avisos:
            print(f"   • {aviso}")

        # Salva mesmo assim, mas com sufixo indicando problema
        caminho_invalido = caminho_saida.replace(".wav", "_INVALIDA.wav")
        print(f"\nArquivo salvo com marcação de problema: {caminho_invalido}")
        print("NÃO envie este arquivo ao Edge Impulse sem regravar.")
        salvar_wav(caminho_invalido, bytes(dados))

    # --- Estatísticas extras ---
    rms  = calcular_rms(bytes(dados))
    pico = calcular_pico(bytes(dados))
    print(f"\n📊 Estatísticas do áudio capturado:")
    print(f"   RMS  : {rms:.0f}  (mínimo recomendado: {RMS_THRESHOLD})")
    print(f"   Pico : {pico}  (mínimo recomendado: {PICO_THRESHOLD})")
    print(f"   Ganho do microfone: gainVal=5 (confirmar no sketch de captura)")


if __name__ == "__main__":
    main()
