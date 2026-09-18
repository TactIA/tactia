#include <TactIA_inferencing.h>
#include <Wire.h>
#include <WiFi.h>
#include "ESP_I2S.h"
#include "pin_config.h"

#define PINO_MOTOR 16
#define SAMPLE_RATE 16000

I2SClass i2s;
const int TAMANHO_BLOCO = 500;
float features[EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE];

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

  uint8_t gainVal = 5;  // GANHO REDUZIDO PARA EVITAR ESTOURO DO ÁUDIO
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

void tarefa_ia(void *pvParameters) {
  int16_t buffer_i2s[TAMANHO_BLOCO * 2];
  String ultima_classe = "";
  int confirmacoes = 0;

  while (1) {
    // 1. JANELA DESLIZANTE
    for (int i = 0; i < 8000; i++) {
      features[i] = features[i + 8000];
    }

    // 2. CAPTURA: Grava apenas os 500ms mais recentes
    for (size_t i = 8000; i < 16000; i += TAMANHO_BLOCO) {
      size_t lidos = i2s.readBytes((char *)buffer_i2s, sizeof(buffer_i2s));
      if (lidos > 0) {
        for (size_t j = 0; j < TAMANHO_BLOCO; j++) {
          features[i + j] = buffer_i2s[j * 2]; // Leitura pura, sem distorção!
        }
      } else {
        for (size_t j = 0; j < TAMANHO_BLOCO; j++) features[i + j] = 0;
      }
    }

    int16_t pico = 0;
    for (int k = 0; k < EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE; k++) {
      int16_t val = abs((int16_t)features[k]);
      if (val > pico) pico = val;
    }
    Serial.printf("Pico de amplitude: %d\n", pico);

    // 3. INFERÊNCIA
    signal_t signal;
    numpy::signal_from_buffer(features, EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE, &signal);
    ei_impulse_result_t result = { 0 };
    run_classifier(&signal, &result, false);

    // =======================================================
    // MODO DEBUG: Vendo os pensamentos da IA em tempo real
    // =======================================================
    Serial.print("🔎 [IA] ");
    for (uint16_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
      Serial.print(result.classification[i].label);
      Serial.print(": ");
      Serial.print(result.classification[i].value, 2);  // Imprime com 2 casas decimais
      Serial.print(" | ");
    }
    Serial.println();  // Pula linha
    // =======================================================

    // 4. LÓGICA DE DECISÃO ADAPTATIVA
    String classe_atual = "";
    float maior_prob = 0;

    // Qual foi a maior probabilidade encontrada?
    for (uint16_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
      if (result.classification[i].value > 0.85 && result.classification[i].value > maior_prob) {
        maior_prob = result.classification[i].value;
        classe_atual = String(result.classification[i].label);
      }
    }

    // Sistema de Confirmação
    if (classe_atual == "buzina" || classe_atual == "sirene" || classe_atual == "alarme" || classe_atual == "campainha") {

      if (classe_atual == ultima_classe) {
        confirmacoes++;
      } else {
        ultima_classe = classe_atual;
        confirmacoes = 1;
      }

      // Agora TODOS precisam de 2 confirmações seguidas
      if (confirmacoes >= 2) {
        Serial.println("=========================================");
        Serial.print("🚨 PERIGO CONFIRMADO: ");
        Serial.println(classe_atual);
        Serial.println("=========================================");

        digitalWrite(PINO_MOTOR, HIGH);
        vTaskDelay(pdMS_TO_TICKS(1000));
        digitalWrite(PINO_MOTOR, LOW);

        confirmacoes = 0;
        ultima_classe = "";
        for (int i = 0; i < 16000; i++) features[i] = 0;  // Limpa áudio
      }
    } else {
      confirmacoes = 0;
      ultima_classe = "";
    }
  }
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_OFF);
  pinMode(PINO_MOTOR, OUTPUT);
  digitalWrite(PINO_MOTOR, LOW);

  Wire1.begin(15, 14);
  es7210_init();

  i2s.setPins(BCLKPIN, WSPIN, DIPIN, DOPIN, MCLKPIN);
  i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH);

  Serial.println("TactIA Iniciado! Escutando em segundo plano...");
  xTaskCreatePinnedToCore(tarefa_ia, "Task_IA", 32768, NULL, 1, NULL, 1);
}

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}