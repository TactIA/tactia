# firmware/inferencia

Sketch "de produção" do TactIA — roda o modelo exportado do Edge
Impulse (TensorFlow Lite Micro) em tempo real, classificando o
áudio captado pelo microfone e disparando os alertas hápticos
(DRV2605L) e visuais (tela AMOLED) conforme a classe detectada.

> **Pendente**: adicionar aqui o(s) arquivo(s) `.ino` de inferência
> atual(is). Ao adicionar, mantenha neste README uma nota da versão
> do modelo em uso (ex: "modelo pós-crop de silêncio, acurácia real
> ~XX% no Model testing") para rastrear qual firmware corresponde a
> qual resultado de treino.

## Diferença em relação a `firmware/captura`

Este sketch **não** envia áudio cru pela serial — ele roda o
classificador localmente no ESP32. Use `firmware/captura` somente
quando for gravar novas amostras de dataset.
