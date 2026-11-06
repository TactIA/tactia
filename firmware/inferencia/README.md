# firmware/inferencia

Sketch "de produção" do TactIA — roda o modelo exportado do Edge
Impulse (TensorFlow Lite Micro) em tempo real, classificando o
áudio captado pelo microfone e disparando os alertas hápticos
(DRV2605L) e visuais (tela AMOLED) conforme a classe detectada.

O sketch é o `inferencia.ino` (o Arduino exige que o arquivo principal tenha o
mesmo nome da pasta). Ele depende da biblioteca `TactIA_inferencing`, exportada
do Edge Impulse em *Deployment > Arduino library*. Use a versão
**Unoptimized (float32)**: no teste por injeção no relógio a versão int8 com
ESP-NN acertou 10,5%, enquanto a float32 acertou 78,3%, reproduzindo o Studio.

O ganho do microfone (`gainVal`) e a taxa de amostragem precisam ser iguais aos
do `firmware/captura`. O CI confere isso a cada push (`tests/test_contratos_firmware.py`).

## Diferença em relação a `firmware/captura`

Este sketch **não** envia áudio cru pela serial — ele roda o
classificador localmente no ESP32. Use `firmware/captura` somente
quando for gravar novas amostras de dataset.
