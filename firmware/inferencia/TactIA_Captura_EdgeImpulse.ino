// =============================================================
// TactIA — INFERÊNCIA (sketch de produção)
// =============================================================
// Roda o modelo Edge Impulse (TFLite Micro) em tempo real,
// classifica sons e aciona vibração háptica via DRV2605L (I2C).
//
// Melhorias aplicadas:
//  - Normalização de features para [-1.0, 1.0] (fix crítico de precisão)
//  - Janela deslizante baseada em EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE
//  - Média dos dois canais do microfone (melhora SNR)
//  - Thresholds por classe calibrados
//  - Votação por janela de 5 frames (sons intermitentes)
//  - Cooldown sem zerar buffer (sons longos/contínuos)
//  - Padrões de vibração distintos por classe via DRV2605L
//  - features[] local na task (sem race condition futura)
// =============================================================

#include <TactIA_inferencing.h>
#include <Wire.h>
#include <WiFi.h>
#include "ESP_I2S.h"
#include "pin_config.h"
#include <Adafruit_DRV2605.h>

// --------------- Pinos / constantes ---------------
#define PINO_MOTOR    16        // usado como fallback se DRV2605L não iniciar
#define SAMPLE_RATE   16000

// Tamanho da meia-janela (shift de 500 ms a 16 kHz)
#define HALF_FRAME    (EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE / 2)

// --------------- Sistema de votação ---------------
#define JANELA_VOTO   5         // últimas N inferências consideradas
#define VOTOS_MINIMOS 3         // mínimo de votos iguais para disparar alerta

// --------------- Thresholds por classe ------------
// Calibre estes valores com a matriz de confusão do Edge Impulse
// (Model Testing → Confusion Matrix). Ordem igual ao label do modelo.
// Classes: alarme | buzina | campainha | sirene  (ordem alfabética padrão EI)
// Se a ordem dos seus labels for diferente, ajuste o array abaixo.
struct ClasseConfig {
  const char *label;
  float      threshold;
  uint8_t    efeito_drv;   // efeito da biblioteca Adafruit DRV2605 (1–123)
  int        pulsos;       // quantos pulsos de vibração
  int        duracao_ms;   // duração de cada pulso em ms
  int        pausa_ms;     // pausa entre pulsos em ms
};

// Referência de efeitos: https://cdn-shop.adafruit.com/datasheets/DRV2605L.pdf pág. 57
static const ClasseConfig CLASSES[] = {
  { "alarme",    0.78f,  14, 4, 150, 100 },  // 4 pulsos rápidos
  { "buzina",    0.80f,  12, 3, 200, 120 },  // 3 pulsos intensos
  { "campainha", 0.82f,  52, 2, 250, 200 },  // 2 pulsos médios
  { "sirene",    0.75f,  58, 1, 800,   0 },  // 1 pulso longo crescente
};
static const int NUM_CLASSES = sizeof(CLASSES) / sizeof(CLASSES[0]);

// --------------- Cooldown após alerta -------------
#define COOLDOWN_MS   3000      // ms sem novo disparo após alerta confirmado

// --------------- Objetos globais ------------------
I2SClass          i2s;
Adafruit_DRV2605  drv;
bool              drv_ok = false;

// =============================================================
// Inicialização do ES7210 (codec / matriz de microfones)
// =============================================================
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

  uint8_t gainVal = 5;  // Ganho reduzido para evitar estouro; ajuste conforme ambiente
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

// =============================================================
// Disparo de vibração: tenta DRV2605L, cai de volta para GPIO
// =============================================================
void vibrar(const ClasseConfig &cfg) {
  Serial.printf("🔔 Padrão háptico: %s (%d pulso(s) de %dms)\n",
                cfg.label, cfg.pulsos, cfg.duracao_ms);

  if (drv_ok) {
    drv.setWaveform(0, cfg.efeito_drv);
    drv.setWaveform(1, 0);  // fim da sequência
    for (int p = 0; p < cfg.pulsos; p++) {
      drv.go();
      vTaskDelay(pdMS_TO_TICKS(cfg.duracao_ms + cfg.pausa_ms));
    }
  } else {
    // Fallback: GPIO direto no motor
    for (int p = 0; p < cfg.pulsos; p++) {
      digitalWrite(PINO_MOTOR, HIGH);
      vTaskDelay(pdMS_TO_TICKS(cfg.duracao_ms));
      digitalWrite(PINO_MOTOR, LOW);
      if (cfg.pausa_ms > 0) vTaskDelay(pdMS_TO_TICKS(cfg.pausa_ms));
    }
  }
}

// =============================================================
// Task de IA — roda inteiramente no Core 1
// features[] é local: sem race condition com expansões futuras
// =============================================================
void tarefa_ia(void *pvParameters) {
  // --- Buffers locais (stack desta task = 32 KB) ---
  float    features[EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE];
  int16_t  buffer_i2s[500 * 2];  // 500 amostras estéreo intercaladas

  // --- Estado da janela de votação ---
  String janela_votos[JANELA_VOTO];
  for (int i = 0; i < JANELA_VOTO; i++) janela_votos[i] = "";
  int    idx_voto    = 0;

  // --- Cooldown ---
  unsigned long cooldown_ate = 0;

  // Inicializa buffer de features com zeros
  memset(features, 0, sizeof(features));

  while (1) {
    // ----------------------------------------------------------
    // 1. JANELA DESLIZANTE — shift de meio segundo
    //    Usa HALF_FRAME derivado de EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE
    //    para funcionar corretamente após qualquer reexportação do modelo.
    // ----------------------------------------------------------
    memmove(features, features + HALF_FRAME,
            HALF_FRAME * sizeof(float));

    // ----------------------------------------------------------
    // 2. CAPTURA — preenche a segunda metade da janela
    //    Média dos dois canais (L+R) / 2 → melhora SNR ~3 dB
    // ----------------------------------------------------------
    const int BLOCO = 500;
    for (int i = HALF_FRAME; i < EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE; i += BLOCO) {
      size_t lidos = i2s.readBytes((char *)buffer_i2s, sizeof(buffer_i2s));
      if (lidos > 0) {
        for (int j = 0; j < BLOCO; j++) {
          // Média dos dois canais, normalizada para [-1.0, 1.0]
          float canal_l = (float)buffer_i2s[j * 2]     / 32768.0f;
          float canal_r = (float)buffer_i2s[j * 2 + 1] / 32768.0f;
          features[i + j] = (canal_l + canal_r) * 0.5f;
        }
      } else {
        memset(&features[i], 0, BLOCO * sizeof(float));
      }
    }

    // Diagnóstico de amplitude (pico absoluto)
    float pico = 0.0f;
    for (int k = 0; k < EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE; k++) {
      float v = fabsf(features[k]);
      if (v > pico) pico = v;
    }
    Serial.printf("Pico de amplitude (normalizado): %.4f\n", pico);

    // ----------------------------------------------------------
    // 3. INFERÊNCIA
    // ----------------------------------------------------------
    signal_t signal;
    numpy::signal_from_buffer(features, EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE, &signal);
    ei_impulse_result_t result = { 0 };
    run_classifier(&signal, &result, false);

    // Modo debug — probabilidades em tempo real
    Serial.print("🔎 [IA] ");
    for (uint16_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
      Serial.printf("%s: %.2f | ",
                    result.classification[i].label,
                    result.classification[i].value);
    }
    Serial.println();

    // ----------------------------------------------------------
    // 4. LÓGICA DE DECISÃO — threshold por classe
    // ----------------------------------------------------------
    String classe_atual = "";
    float  maior_prob   = 0.0f;

    for (uint16_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
      float prob  = result.classification[i].value;
      const char *lbl = result.classification[i].label;

      // Busca threshold específico desta classe
      float thr = 0.85f;  // fallback conservador
      for (int c = 0; c < NUM_CLASSES; c++) {
        if (strcmp(CLASSES[c].label, lbl) == 0) {
          thr = CLASSES[c].threshold;
          break;
        }
      }

      if (prob > thr && prob > maior_prob) {
        maior_prob   = prob;
        classe_atual = String(lbl);
      }
    }

    // ----------------------------------------------------------
    // 5. VOTAÇÃO POR JANELA DE 5 FRAMES
    //    Registra resultado (ou "" se nenhuma classe passou o threshold)
    //    e só dispara se ≥ VOTOS_MINIMOS frames concordarem.
    // ----------------------------------------------------------
    janela_votos[idx_voto % JANELA_VOTO] = classe_atual;
    idx_voto++;

    // Conta votos para cada classe na janela
    String classe_vencedora = "";
    int    max_votos         = 0;
    for (int c = 0; c < NUM_CLASSES; c++) {
      int votos = 0;
      for (int v = 0; v < JANELA_VOTO; v++) {
        if (janela_votos[v] == String(CLASSES[c].label)) votos++;
      }
      if (votos > max_votos) {
        max_votos        = votos;
        classe_vencedora = String(CLASSES[c].label);
      }
    }

    // ----------------------------------------------------------
    // 6. DISPARO — cooldown impede reativação sem zerar o buffer
    // ----------------------------------------------------------
    if (max_votos >= VOTOS_MINIMOS && millis() > cooldown_ate) {
      // Localiza config da classe vencedora
      int cfg_idx = -1;
      for (int c = 0; c < NUM_CLASSES; c++) {
        if (classe_vencedora == String(CLASSES[c].label)) { cfg_idx = c; break; }
      }

      Serial.println("=========================================");
      Serial.printf("🚨 PERIGO CONFIRMADO: %s (%d/%d votos)\n",
                    classe_vencedora.c_str(), max_votos, JANELA_VOTO);
      Serial.println("=========================================");

      if (cfg_idx >= 0) vibrar(CLASSES[cfg_idx]);

      // Inicia cooldown e limpa janela de votos (sem tocar no buffer de áudio)
      cooldown_ate = millis() + COOLDOWN_MS;
      for (int v = 0; v < JANELA_VOTO; v++) janela_votos[v] = "";
      idx_voto = 0;
    }
  }
}

// =============================================================
// Setup
// =============================================================
void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_OFF);

  // Motor GPIO (fallback)
  pinMode(PINO_MOTOR, OUTPUT);
  digitalWrite(PINO_MOTOR, LOW);

  // DRV2605L via I2C principal (SDA/SCL padrão do ESP32-S3)
  Wire.begin();
  if (drv.begin()) {
    drv.selectLibrary(1);
    drv.setMode(DRV2605_MODE_INTTRIG);
    drv_ok = true;
    Serial.println("DRV2605L inicializado com sucesso.");
  } else {
    Serial.println("⚠️  DRV2605L não encontrado — usando GPIO direto no motor.");
  }

  Wire1.begin(15, 14);
  es7210_init();

  i2s.setPins(BCLKPIN, WSPIN, DIPIN, DOPIN, MCLKPIN);
  i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT,
            I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH);

  Serial.println("TactIA Iniciado! Escutando em segundo plano...");
  xTaskCreatePinnedToCore(tarefa_ia, "Task_IA", 32768, NULL, 1, NULL, 1);
}

// =============================================================
// Loop principal — livre para LVGL / BLE no futuro
// =============================================================
void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}
