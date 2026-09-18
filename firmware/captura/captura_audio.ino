// =============================================================
// TactIA — CAPTURA (não é o sketch de inferência!)
// =============================================================
// Este sketch só existe para gravar amostras de áudio cru e
// alimentar o script captura_audio.py. Ele NÃO roda o
// classificador — a ideia é manter o loop leve e rápido o
// suficiente para não perder amostras.
//
// IMPORTANTE:
//  - O baud rate aqui (921600) tem que ser EXATAMENTE igual ao
//    BAUD_RATE do script Python.
//  - O áudio é enviado como int16 little-endian (binário, 2 bytes
//    por amostra) via Serial.write() — NÃO use Serial.println().
//  - O canal enviado é a MÉDIA dos dois canais (L+R)/2, truncada
//    para int16, idêntico ao processamento do firmware de inferência.
//    Isso garante que o dataset represente exatamente o que a IA vê.
//  - Depois de gravar o dataset, volte para o sketch de
//    inferência normal.
// =============================================================

#include <Wire.h>
#include "ESP_I2S.h"
#include "pin_config.h"

#define SAMPLE_RATE    16000
#define TAMANHO_BLOCO  500

I2SClass i2s;

void es7210_init() {
  uint8_t addr = 0x40;
  auto writeReg = [&](uint8_t reg, uint8_t val) {
    Wire1.beginTransmission(addr);
    Wire1.write(reg);
    Wire1.write(val);
    Wire1.endTransmission();
  };
  auto readReg = [&](uint8_t reg) -> uint8_t {
    Wire1.beginTransmission(addr);
    Wire1.write(reg);
    Wire1.endTransmission(false);
    Wire1.requestFrom((int)addr, 1);
    return Wire1.available() ? Wire1.read() : 0;
  };
  auto updateBits = [&](uint8_t reg, uint8_t mask, uint8_t data) {
    uint8_t v = readReg(reg);
    v = (v & ~mask) | (mask & data);
    writeReg(reg, v);
  };

  writeReg(0x00, 0xFF);
  writeReg(0x00, 0x32);
  writeReg(0x01, 0x3F);
  writeReg(0x09, 0x30);
  writeReg(0x0A, 0x30);
  writeReg(0x23, 0x2A);
  writeReg(0x22, 0x0A);
  writeReg(0x20, 0x0A);
  writeReg(0x21, 0x2A);
  updateBits(0x08, 0x01, 0x00);
  writeReg(0x40, 0xC3);
  writeReg(0x41, 0x70);
  writeReg(0x42, 0x70);
  writeReg(0x11, 0x60);
  writeReg(0x12, 0x00);
  writeReg(0x02, 0xC1);
  writeReg(0x07, 0x20);
  writeReg(0x04, 0x01);
  writeReg(0x05, 0x00);

  // IMPORTANTE: este gainVal deve ser IDÊNTICO ao usado no sketch de inferência.
  // Qualquer diferença de ganho entre dataset e inferência invalida a
  // consistência espectral e degrada a acurácia do modelo.
  uint8_t gainVal = 5;
  updateBits(0x43, 0x10, 0x00);
  updateBits(0x44, 0x10, 0x00);
  writeReg(0x4B, 0xFF);
  updateBits(0x01, 0x0B, 0x00);
  writeReg(0x4B, 0x00);
  updateBits(0x43, 0x10, 0x10);
  updateBits(0x43, 0x0F, gainVal);
  updateBits(0x01, 0x0B, 0x00);
  writeReg(0x4B, 0x00);
  updateBits(0x44, 0x10, 0x10);
  updateBits(0x44, 0x0F, gainVal);
  writeReg(0x47, 0x08);
  writeReg(0x48, 0x08);
  writeReg(0x06, 0x04);
  writeReg(0x4B, 0x0F);
  writeReg(0x00, 0x71);
  writeReg(0x00, 0x41);
}

void setup() {
  // PRECISA bater com BAUD_RATE do captura_audio.py (921600)
  Serial.begin(921600);
  while (!Serial) { delay(10); }

  Wire1.begin(15, 14);
  es7210_init();

  i2s.setPins(BCLKPIN, WSPIN, DIPIN, DOPIN, MCLKPIN);
  i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT,
            I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH);

  delay(500);
  // Não imprima nada além dos bytes de áudio aqui —
  // o Python lê bytes brutos e qualquer dado extra corrompe o .wav.
}

void loop() {
  int16_t buffer_i2s[TAMANHO_BLOCO * 2];  // estéreo intercalado
  size_t lidos = i2s.readBytes((char *)buffer_i2s, sizeof(buffer_i2s));

  if (lidos > 0) {
    size_t amostras_lidas = lidos / sizeof(int16_t);
    for (size_t j = 0; j + 1 < amostras_lidas; j += 2) {
      // Mesma operação do firmware de inferência:
      // média dos dois canais → int16 little-endian
      int32_t media = ((int32_t)buffer_i2s[j] + (int32_t)buffer_i2s[j + 1]) / 2;
      int16_t amostra = (int16_t)media;
      Serial.write((uint8_t *)&amostra, 2);
    }
  }
}
