# TactIA

Bem-vindo ao TactIA!

O **TactIA** é um smartwatch assistivo com inteligência artificial embarcada, desenvolvido para pessoas com deficiência auditiva severa ou profunda. O dispositivo detecta e classifica sons relevantes do ambiente — como buzinas, campainhas e sirenes — e transmite alertas ao usuário por meio de padrões de vibração háptica no pulso, promovendo maior segurança e autonomia no dia a dia.

O projeto foi desenvolvido como **Projeto Integrador 2026**, com metodologia aplicada e experimental, desenvolvimento iterativo de hardware e software, e validação direta com usuários do público-alvo.

## Problema

Segundo a **Organização Mundial da Saúde (OMS)**, mais de 1,5 bilhão de pessoas vivem com algum grau de perda auditiva globalmente. No Brasil, o Censo Demográfico do IBGE aponta que aproximadamente **10,7 milhões de pessoas** possuem deficiência auditiva, representando cerca de 5% da população nacional.

As soluções existentes no mercado apresentam limitações importantes:

- **Aparelhos auditivos** amplificam sons indiscriminadamente, sem classificá-los por relevância;
- **Aplicativos de smartphone** exigem que o usuário esteja constantemente olhando para a tela.

O TactIA surge para preencher essa lacuna: um dispositivo vestível compacto, de baixo custo, com processamento de IA local e resposta háptica imediata.

## Alinhamento com os ODS da ONU

O TactIA está alinhado aos seguintes Objetivos de Desenvolvimento Sustentável da Agenda 2030:

- **ODS 10 – Redução das Desigualdades**: promoção da inclusão social de pessoas com deficiência auditiva;
- **ODS 3 – Saúde e Bem-Estar**: aumento da segurança e da qualidade de vida do público-alvo.

## Benchmarking

| Solução | Descrição | Limitação |
|---|---|---|
| Starkey Livio AI | Aparelho auditivo com IA | Custo acima de R$ 8.000; foco em amplificação, não em classificação |
| Bellman & Symfon | Sistema de alertas visuais residenciais | Limitado ao ambiente doméstico, sem mobilidade |
| Sound Alert (app) | App de detecção de sons com notificações visuais | Exige tela ativa; sem feedback háptico dedicado |
| **TactIA ✓** | **Smartwatch com IA embarcada, vibração háptica e alertas visuais** | **Protótipo em desenvolvimento** |

## Tecnologia

### Hardware

A base do sistema é a **placa Waveshare ESP32-S3-Touch-AMOLED-1.75**, que integra:

- Microcontrolador **ESP32-S3 dual-core** com capacidade de executar modelos de IA localmente;
- Tela **AMOLED tátil circular** de 1,75" (466×466 px);
- Chip de gerenciamento de energia **AXP2101**;
- Matriz dupla de microfones com chip de cancelamento de eco **ES7210**.

Demais componentes:

- **Motor de Vibração tipo Moeda (1027)**: resposta háptica no pulso;
- **Driver Háptico DRV2605L**: controle via I2C com dezenas de padrões de vibração de alta precisão;
- **Bateria Li-Po 3.7V** (tamanho 502030 ou 602030) com conector JST 1.25mm;
- **Carcaça impressa em 3D** para acomodação compacta de todos os componentes.

### Software e Inteligência Artificial

| Camada | Tecnologia |
|---|---|
| Firmware | C/C++ (Arduino IDE / ESP-IDF) |
| Interface Gráfica | Biblioteca LVGL |
| Inteligência Artificial | Edge Impulse / TensorFlow Lite Micro |
| Comunicação de Hardware | Barramento I2C |
| Carcaça | Modelagem 3D |

O modelo de classificação de sons é treinado na plataforma **Edge Impulse** com datasets públicos (UrbanSound8K e ESC-50) e gravações próprias, utilizando extração de características **MFCC** e modelos leves como o **MobileNet**. A inferência ocorre **100% offline**, garantindo baixa latência e privacidade ao usuário.

As classes de sons detectadas são: `buzina`, `campainha`, `sirene de emergência`, `alarme` e `ambiente (sem alerta)`.

### Arquitetura do Sistema

O sistema é dividido em três camadas:

```
┌──────────────────────────────────────────────────┐
│  Camada de Percepção                             │
│  Microfones com cancelamento de ruído (ES7210)   │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│  Camada de Inteligência                          │
│  ESP32-S3 – classificação offline em tempo real  │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│  Camada de Atuação                               │
│  DRV2605L (vibração háptica) + tela AMOLED       │
└──────────────────────────────────────────────────┘
```

## Casos de Uso

| Som Detectado | Padrão de Vibração | Tela |
|---|---|---|
| 🚗 Buzina de veículo | Três vibrações intensas | Ícone de buzina |
| 🔔 Campainha | Vibrações curtas pulsadas | Ícone animado |
| 🚨 Sirene de emergência | Vibração contínua de alerta máximo | Alerta visual de emergência |
| 🔕 Modo silencioso | Vibrações desativadas | Configuração via toque |

## Estrutura do repositório

```
tactia/
├── README.md
├── firmware/
│   ├── captura/          → sketch usado só para gravar dataset (envia áudio cru pela serial)
│   └── inferencia/       → sketch "de produção", roda o modelo classificador no ESP32
├── tools/
│   └── captura_audio.py  → script Python que recebe o áudio da serial e salva em .wav
├── model/                → biblioteca exportada do Edge Impulse (opcional, versionar por marco)
└── docs/
    └── relatorios/       → prints e relatórios de treino, histórico de resultados
```

Cada subpasta de `firmware/` tem seu próprio `README.md` explicando o propósito e os requisitos do sketch correspondente.

## Projeto

O desenvolvimento do TactIA segue uma metodologia iterativa, com as seguintes fases ao longo de 2026:

| Período | Atividade |
|---|---|
| Janeiro – Fevereiro | Revisão bibliográfica e importação do hardware |
| Março – Abril | Integração do driver DRV2605L, implementação da biblioteca LVGL e interface gráfica básica |
| Maio – Junho | Coleta de dados de áudio, treinamento e compilação do modelo de IA via Edge Impulse |
| Julho – Agosto | Modelagem e impressão da carcaça 3D, montagem compacta do hardware |
| Setembro – Outubro | Testes de campo e validação de usabilidade com o público-alvo (escala SUS) |
| Novembro – Dezembro | Refinamentos finais, documentação e apresentação na FETEPS |

## Orçamento

Estimativa de custo para produção do protótipo unitário:

| Componente | Custo |
|---|---|
| Placa Waveshare ESP32-S3-Touch-AMOLED-1.75" | R$ 300,00 |
| Módulo Driver Háptico DRV2605L | R$ 40,00 |
| Bateria Li-Po 3.7V (400mAh) com conector JST | R$ 35,00 |
| Micromotor de vibração tipo Moeda 1027 | R$ 10,00 |
| Fiação e insumos de impressão 3D | R$ 20,00 |
| **TOTAL** | **R$ 405,00** |

O custo de desenvolvimento está estimado em **280 horas** distribuídas entre programação de interface (50h), integração e drivers (30h), treinamento de IA (60h), modelagem 3D (30h), testes (60h) e documentação (50h).

## Stakeholders

- **Usuários primários**: pessoas com deficiência auditiva severa ou profunda;
- **Familiares e cuidadores**: beneficiados pela maior autonomia e segurança dos usuários;
- **Associações e instituições de apoio a surdos**: potenciais parceiros de validação;
- **Equipe de desenvolvimento**: responsável pela integração de hardware, design 3D, firmware e IA.

## Contato

Em caso de dúvidas e sugestões, entre em contato com a equipe de desenvolvimento através das _issues_ deste repositório.
