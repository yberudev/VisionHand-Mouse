> Ciclo rápido e tolerância do punho — 16/11/2026: análise da sessão `session-fist.jsonl` (3369 frames) encontrou 13 downs/13 ups e **zero cliques simples**, 23 timeouts de incerteza e várias aberturas canceladas. Entre os frames OTHER com geometria havia 40 com quatro dedos compactos que falhavam apenas o limite do polegar; exemplos tinham distância normalizada 1.02–1.05 contra o limite antigo 0.95. Sem intenção rotulada, estes dados não dão taxa de falsos cliques.
>
> Implementação: detetor específico de ciclo com confirmação inicial de 20 ms e pelo menos duas amostras para fechar/reabrir, independente dos 45 ms do estabilizador geral. Quatro dedos reabertos completam o ciclo mesmo com polegar ainda recolhido; a pose de pausa substituta só pausa se mantida por 350 ms em MOVE. Ciclo de toque limitado a 600 ms reais; perfil `calibration.fist.json` com hold de 750 ms. Cancelamentos/perda não geram clique e um hold termina só com up. Escala geométrica do punho passa a usar os três spans robustos da palma, limite do polegar ajustado, aquisição com quatro evidências de flexão (uma pode estar fora do raio estrito) e retenção de um dedo incerto sem aceitar dedo estendido ou cadeia degenerada. HUD permanece durante confirmação de pausa, até esta ser efetiva.
>
> **115 testes passaram nos dois intérpretes.** Novos casos cobrem ciclo rápido em 15/30/60/120 FPS, poses intermédias, abertura com polegar tardio, rejeição de um único frame fechado, hold sem clique adicional, perda no ciclo, longa ambiguidade sem clique, tolerância espacial de polegar/dedo, retenção sem aquisição indevida e gravação/replay de uma sequência de landmarks com exatamente um clique. Adicionados `--record-landmarks`, diagnóstico de fase de ciclo e replay puro offline em `tools/replay_landmarks.py`; logs antigos não foram reconstituídos em landmarks fictícios. Não houve teste humano de clique com webcam desta versão. A próxima sessão pode ser gravada em `session-pulse.jsonl` para comparação exata e calibração com intenções anotadas; não foi alegada resolução definitiva com mão real.

> Reconhecimento de punho — 16/11/2026: após o relato de punho classificado como desconhecido, identificada regra rígida que exigia cinco estados booleanos definitivamente recolhidos, incluindo o polegar. Substituído o caso FIST por evidência específica de quatro dedos fechados/compactos e polegar dentro de uma região compacta da palma. Dedos arredondados com ângulos na zona anteriormente ambígua só são aceites com compactação adicional da cadeia e proximidade da ponta à palma/MCP. Polegar claramente estendido, qualquer dedo estendido e cadeia degenerada continuam rejeitados como punho; UNKNOWN não é convertido genericamente em FIST. Diagnóstico mostra quatro evidências de fecho e compactação do polegar; `geometry` no JSONL inclui as medições usadas, sem imagens.
>
> Validação: **104 testes passaram nos dois intérpretes**. Sete testes novos incluem polegar próximo mas angularmente ambíguo, dedos arredondados, 48 combinações de rotação/espelhamento/escala, rejeição de um dedo estendido, thumbs-up e cadeias colapsadas, e sequência completa de landmarks que gera exatamente um clique. O caso de polegar ambíguo apresenta `thumb_state=None` com quatro dedos compactos e agora é FIST. Não foi recolhida nem validada a pose real que falhou para o utilizador: os logs existentes não continham as medições geométricas agora adicionadas. A correção remove uma causa concreta possível, mas a confirmação final requer novo ensaio com a webcam.

> Experimento de clique com punho — 16/11/2026: acrescentada a flag `--fist-click` e a configuração persistível `left_click_gesture`. O modo usa punho fechado para clique esquerdo/hold, mão aberta para mover/libertar e polegar recolhido com quatro dedos estendidos para pausa confirmada. Reconhecimento geométrico continua a reportar poses físicas (FIST/LEFT); o motor liga a ação conforme a configuração. Painel e logs adaptam-se ao mapeamento. O mapeamento anterior permanece disponível sem a flag e sem modificar os perfis pessoais. F8/F9 e libertação por perda continuam ativos.
>
> Validação: **97 testes passaram nos dois intérpretes**, incluindo 12 testes novos de toque único/duplo com landmarks de punho, hold com movimento/libertação, cancelamento por pausa substituta, perda da mão, recuperação inicial, clique direito, persistência, conflito de bindings e transições intermédias de fechar a mão. Nenhum evento real de rato foi emitido nesta alteração. Ainda falta ensaio humano com webcam deste mapeamento.

> Persistência da mira após minimizar — 16/11/2026: o teste inicial de minimizar isoladamente passou, mas o teste com restaurar/reordenar janelas reproduziu pixels da mira ocultos apesar do indicador de visibilidade positivo. Corrigida a criação explícita com WS_EX_TOPMOST, verificação real de visibilidade/minimização e reposição periódica do z-order sem ativação, com nova pintura após recuperação. A elegibilidade visual também mantém a mira durante confirmação/tolerância de gesto, sem alterar eventos de rato ou segurança. A pré-visualização Windows verifica a existência do HWND em vez de inferir encerramento por visibilidade, e consome/descarta frames sem repintar quando está minimizada. Logs incluem o estado e erros do HUD; procura de janelas é limitada ao PID para não atuar sobre outra instância.
>
> Validação: **85 testes passaram nos dois intérpretes**. `tools/smoke_hud.py` passou em estilos, transparência a hit-test, pixel verde, foco preservado, pausa e expiração de heartbeat. Novo `tools/smoke_minimize.py` passou em três ciclos reais minimizar/restaurar, ocultação e minimização externa do HUD, recuperação de z-order, pixels verdes, foco preservado, continuidade da pré-visualização e encerramento explícito. Os ensaios atuaram apenas sobre as janelas criadas pelo próprio teste e não emitiram input de rato nem usaram webcam. A estabilidade numa sessão prolongada com os gestos reais do utilizador continua a precisar de confirmação; fullscreen exclusivo/desktop seguro continuam fora da garantia.

> Mira no cursor — 16/11/2026: implementação em `cursor_hud.py`, integrada em `main.py`, com testes em `tests/test_cursor_hud.py` e `tools/smoke_hud.py`. HUD nativo Windows por GDI, caixa 64 × 64 centrada no cursor, quatro guias verdes, fundo transparente, topmost, click-through e sem ativação. Processo isolado com heartbeat; pausa/perda/incerteza ocultam a mira, e expiração do heartbeat também a esconde. `--no-hud` desativa o efeito; só inicia por padrão em live/Windows. Não altera reconhecimento, limiares nem eventos do rato.
>
> Validação: **84 testes passaram nos dois intérpretes**, incluindo a adaptação que isola falhas da mira do motor de controlo. Teste real Win32: estilos corretos, mesmo HWND em primeiro plano antes/depois, hit-test na linha retorna uma janela subjacente, pixel verde esperado na borda da caixa, ocultação por pausa e por heartbeat expirado. Nenhum clique ou deslocamento foi injetado neste teste. A primeira tentativa com Tk foi rejeitada pelo teste por mudar o foco e foi substituída pela janela Win32 nativa. Ainda falta validar preferência visual, distração e impacto de desempenho numa sessão prolongada de webcam; não foi afirmado custo de desempenho nulo.

> Calibração de clique/hold/distância — 16/11/2026: análise de `session-live.jsonl` (1151 frames) encontrou 4 downs, 4 ups, nenhum clique simples; todos os holds foram libertados por OTHER. Dois duraram apenas 32 e 65 ms. Um down foi ativado com 226 ms de pending por deslocamento, antes do antigo limiar de duração. São observações do log; sem intenção rotulada não se pode chamar a todos eles falsos cliques. O resumo reproduzível está em `calibration_log_summary.json`, gerado por `tools/analyze_session.py`.
>
> Alterações: defaults/perfil conservador com tap_ms=450, drag_ms=650, drag_distance=0.18 e drag_confirm_ms=100. Distância não ativa hold durante a janela de toque. Incerteza breve em pending/hold congela movimento, não conta para o temporizador e permite recuperar em até 180 ms; exceder o prazo cancela/liberta. Perda, punho e desativação continuam imediatos. Escala de movimento usa mediana de três spans da palma, suavização de 250 ms e faixa de aceitação 0.07–0.70; painel mostra proximidade excessiva/insuficiente e progresso do pending. Novos campos de diagnóstico explicam escala e causa de ativação. Perfil persistente: `calibration.precise.json`.
>
> Validação: **80 testes passaram nos dois intérpretes**. Casos novos cobrem o falso hold sintético aos 226 ms, toques com deslocamento em 15–120 FPS, confirmação de distância, clique com OTHER na abertura do polegar, continuidade após UNKNOWN breve, timeout, ausência de contagem temporal durante incerteza, perda/punho durante tolerância e tamanhos extremos. O mesmo percurso físico sintético a escalas 0.5, 1.0 e 1.8 produziu deslocamento X lógico de 0.40847938 nos três casos; isto demonstra invariância no modelo sintético, não garante invariância real de perspetiva. Os testes anteriores com duração fixa de 350 ms foram atualizados para o novo limiar e trajetórias contínuas. Ainda falta recolher uma nova sessão de webcam com intenção rotulada e comparar toques/holds/distâncias; não foi alegada resolução definitiva com mão real. O log original foi preservado.

> Correção de bloqueio/foco em 15/11/2026: após o utilizador confirmar bloqueio ao arrastar a própria janela e continuação do reconhecimento sem resposta noutras aplicações, a pré-visualização foi isolada num processo com fila de um frame. O controlador deixou de executar `imshow`/`waitKey`. No Windows, o backend padrão passou a SendInput com retorno verificado, coordenadas absolutas do desktop virtual e configuração de DPI; a opção PyAutoGUI permanece disponível. F8 pausa/retoma e F9 encerra sem depender do foco da pré-visualização no desktop normal. Diagnóstico inclui motivo de paragem, backend, aceitação, número de eventos e PID em primeiro plano; falhas explícitas são gravadas e propagadas com tentativa de limpeza. Novos ficheiros: `window.py`, `hotkeys.py`, `wininput.py`, `tests/test_desktop.py`, `tools/smoke_desktop.py`.
>
> Validação desta correção: 67 testes passaram nos dois intérpretes; inclui processo de preview deliberadamente bloqueado enquanto um arrastamento sintético move e liberta o botão, mudanças simuladas de primeiro plano, ABI nativa (INPUT de 40 bytes neste Windows x64), SendInput rejeitado, monitores com origem negativa, scroll assinado, limpeza e hotkeys sem repetição. O smoke desktop real apresentou um frame no processo filho e o Windows aceitou um evento sem deslocamento intencional, sem cliques/holds/scroll. O smoke da aplicação processou cinco frames reais, todos sem mão, sem eventos de rato, com inferências de 40.349, 36.700, 41.818, 51.668 e 46.817 ms. O log antigo disponível tinha 2452 frames e nenhum clique/down/drag: não permite atribuir a falha noutras aplicações a uma causa comprovada. A migração do backend remove retornos ignorados da implementação anterior; a validação com as aplicações reais do utilizador continua pendente. Não se contornam restrições UIPI ou do desktop seguro. [Documentação SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput); [ciclo modal de janela](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-entersizemove).

> Atualização dos gestos em 15/11/2026, pelas três imagens fornecidas: esquerdo = polegar recolhido e quatro dedos estendidos; direito = indicador recolhido, polegar e restantes três estendidos; scroll = pinça OK entre polegar/indicador com restantes três estendidos. Mão aberta continua a mover e punho fechado a pausar. IDs de diagnóstico: LEFT, RIGHT, SCROLL. O sinal OK tem prioridade sobre o clique direito e usa histerese configurável (0.30/0.42 larguras de palma). Foram executados 56 testes, todos passaram nos dois intérpretes. Incluem oposição do polegar na palma, prioridade/histerese/reset de pinça, rejeição dos gestos antigos e cancelamento entre clique e scroll. As três capturas de ecrã foram lidas localmente; o MediaPipe não voltou a detetar mãos nelas (nem nos recortes exploratórios com limiar reduzido). Portanto, a correspondência foi implementada pela postura visual e validada com landmarks sintéticos, sem alegar validação automática das fotografias ou teste ao vivo. Nenhum evento real de rato foi emitido nesta atualização.

> Atualização experimental em 15/11/2026: o padrão passou a mão aberta para mover e punho fechado para pausar. Os 46 testes anteriores foram adaptados ao novo mapeamento e foram acrescentados quatro testes de pausa imediata/libertação e compatibilidade com o modo original: 50 testes passam. O restante relatório abaixo descreve a auditoria original de 14/11. `move_gesture=FIST` permite comparar os dois modos. Ainda não houve validação humana deste novo mapeamento com webcam.

# Auditoria e validação — Invisible Mouse 0.2

Data: 14/11/2026. Implementação local, sem novas dependências. Esta pasta não contém metadados Git; não foi possível apresentar um diff/commit Git. A fonte original do motor foi preservada como fixture de comparação.

## 1. Causas identificadas

1. `main.py` calculava `(centro_x / escala, centro_y / escala)`. Mesmo com centro fixo, variações de escala alteravam a posição; isso convertia ruído de profundidade/tamanho em deslocamento lateral.
2. `Engine._move` atualizava a referência antes da dead zone. Todo deslocamento abaixo de 0.012 por frame era descartado, mesmo numa trajetória lenta contínua. A interpretação dependia de FPS.
3. Não existiam filtros temporais de movimento, rejeição de outliers nem estabilização temporal dos gestos.
4. A classificação considerava sobretudo distâncias ao punho. Não usava ângulos nem distinguia mão aberta de gesto desconhecido.
5. O início de arrastamento descartava explicitamente o percurso pendente. `double_ms` não era utilizado e não havia diagnóstico de pares de cliques.
6. O scroll acumulava qualquer oscilação vertical, sem dead zone própria.
7. A captura/inferência/interface eram síncronas. Não havia idade de frame, persistência de calibração nem métricas por etapa.
8. A limpeza dependia da emissão normal de `mouseUp`: o failsafe podia bloquear a libertação. Não existia propriedade de botões separada do motor.
9. Os sete testes originais passavam, mas dois usavam saltos temporais de 390/490 ms como se houvesse observações contínuas. Foram substituídos por sequências contínuas; um teste separado comprova que um intervalo sem frames provoca cancelamento seguro.

## 2. Implementação

- Centro da palma usando punho e quatro MCP; diferenças entre centros normalizadas pela escala média entre frames, com correção da proporção da imagem.
- One Euro com derivada filtrada e abertura proporcional à velocidade. Rejeição de velocidade anormal, variação abrupta de escala e geometria degenerada. Landmarks digitais espúrios são ainda contidos pela confirmação temporal.
- Dead zone adaptativa e âncora persistente: o movimento lento acumula até ultrapassar o limiar. Aceleração usa velocidade entre amostras; frações de pixel não se perdem no backend.
- Classificação 3D por ângulos articulares, alcance normalizado, abertura do polegar e validade da palma. Histerese e banda de incerteza; gesto desconhecido nunca é promovido a punho.
- Máquina explícita para clique, hold, drag, scroll, pausa e perda. Percurso pendente é preservado ao iniciar drag, com limite por atualização. Pausas/reentrada reinicializam a referência.
- Exatamente um clique por toque; dois toques produzem dois cliques nativos. O agrupamento interno usa `double_ms`; reconhecimento final do duplo clique pertence ao SO.
- Cancelamento seguro em perda, outlier, mudança de mão, desativação e exceções; backend controla os botões que possui e tenta libertá-los mesmo com failsafe ativo.
- Captura numa thread com slot único. Frames antigos são rejeitados antes da emissão. Sem fila crescente de frames na aplicação.
- Configuração JSON validada, editor de calibração no terminal, overrides CLI e gravação atómica. Diagnóstico visual e JSONL sem guardar imagens.

## 3. Ficheiros

Modificados: `engine.py`, `main.py`, `tests/test_engine.py`, `README.md`.

Adicionados: `config.py`, `motion.py`, `gestures.py`, `controller.py`, `backends.py`, `capture.py`, `diagnostics.py`, `calibration.example.json`, `tests/synthetic.py`, `tests/test_pipeline.py`, `tests/test_integration.py`, `tests/baseline_engine.py`, `tools/benchmark.py`, `tools/smoke_test.py`, `tools/smoke_app.py`, `benchmark_results.json`, `VALIDATION.md`, `.gitignore`.

`requirements.txt` e o modelo existente foram mantidos. Não foram introduzidos serviços externos ou downloads automáticos.

## 4. Testes executados

- Antes da alteração: **7 testes passaram**.
- Depois: **46 testes passaram** em Python 3.14.10 global e no Python da `.venv`.
- `python -m py_compile` nos módulos da aplicação e ferramentas: sucesso.
- CLI `python main.py --help`: sucesso, sem importar dependências de câmara.
- Modelo real: cinco imagens pretas processadas, nenhuma mão detetada.
- Webcam 0 real: cinco frames capturados e processados, nenhuma mão detetada. Não se guardaram imagens nem se emitiram eventos do rato.
- Ciclo real de `main.py` com webcam, modelo, thread de captura e JSONL: cinco frames; estado `LOST_HAND` nos cinco; zero eventos. Apenas `imshow` e leitura de teclas foram substituídos por mocks para fechar automaticamente; captura/inferência/controlo/log/cleanup foram executados. O log temporário foi eliminado ao terminar. A renderização visual da janela não foi verificada.

Cobertura: mão parada; movimento lento/rápido; pausa/reposicionamento; toque único/duplo; hold esquerdo/direito; libertação; scroll nos dois sentidos e com ruído; desconhecidos; flapping; perda/reentrada; FPS 15/30/60/120; rotação, espelhamento e escala; outliers; configuração; JSONL; frações de pixel; erros de backend e failsafe. São sequências sintéticas, não uma amostra representativa de mãos reais.

## 5. Medições reproduzíveis

Comando: `python tools/benchmark.py`. Duração por cenário: 5 s; 60 FPS; seed 42. Motor original preservado em `tests/baseline_engine.py`. Centro estacionário com ruído uniforme de ±0.0005 e escala de palma 0.24 com oscilação senoidal de ±2.5%. Não há webcam neste benchmark.

| Cenário | Original | 0.2 |
|---|---:|---:|
| Estacionário: eventos move | 91 | 0 |
| Estacionário: percurso lógico emitido | 2.140746 | 0 |
| Lento (0.012 coordenadas/s): eventos move | 0 | 279 |
| Lento: deslocamento X lógico | 0 | 0.400665 |
| Rápido (0.12 coordenadas/s): eventos move | 0 | 296 |
| Rápido: deslocamento X lógico | 0 | 4.886582 |

A versão original descarta mesmo o cenário rápido a 60 FPS porque cada incremento ainda é inferior à sua dead zone. As unidades são as dos eventos do motor, anteriores à conversão para pixels. Sensibilidade, aceleração e conversão final mudaram: estes números não são uma comparação de precisão em pixels nem de usabilidade.

Variação com FPS no movimento lento da versão 0.2:

| FPS | Deslocamento X lógico |
|---:|---:|
| 15 | 0.401124 |
| 30 | 0.400814 |
| 60 | 0.400665 |
| 120 | 0.400783 |

Amplitude relativa ao menor resultado: aproximadamente **0.115%** neste cenário. O teste de FPS de hold confirma ativação na primeira amostra após o limiar, dentro de um período de frame.

Tempos observados, sem alegar melhoria sobre a versão anterior:

- Inferência sobre imagens pretas: 227.060 ms na primeira chamada; 42.882–51.657 ms nas quatro seguintes.
- Probe de webcam: primeira leitura 1728.477 ms; seguintes 2.599–41.711 ms. Inferência: 35.957–42.441 ms.
- Ciclo completo da aplicação, cinco frames sem mão: inferências 48.935, 41.460, 55.952, 39.635 e 43.736 ms.

Amostras pequenas e sem landmarks de mão não medem latência típica de rastreamento. Não foi medido desempenho anterior de inferência/captura, latência física ponta a ponta ou consumo de CPU. O MediaPipe emitiu avisos sobre feedback tensors e NORM_RECT durante o smoke test; não impediram a execução, mas o probe sem mão não valida projeção de landmarks reais.

## 6. Limitações conhecidas

- Classificação heurística conservadora, sem validação com participantes. Histerese temporal acrescenta a janela configurada e quantização de um frame.
- Gesto desconhecido durante drag liberta imediatamente: pode causar interrupções em oclusão/pose difícil. A prioridade é impedir ações involuntárias.
- A compensação de escala corrige a falha algébrica original; não é um modelo completo de perspetiva, rotação fora do plano ou profundidade.
- O centro usa média de cinco landmarks. Ruído correlacionado e outliers pequenos podem atravessar o filtro; saltos grandes são rejeitados ao nível da observação. Não há confiança individual de landmarks disponível nesta interface.
- A certeza apresentada é binária e geométrica, não uma probabilidade calibrada de acerto. Seleção da mão usa o rótulo do modelo na imagem após espelhamento, sem identidade pessoal.
- `double_ms` reconhece pares internamente, mas não altera configurações globais nem força o SO a aceitar um duplo clique fora do intervalo/tolerância espacial nativos.
- Não há garantia de libertação num kill do processo, bloqueio indefinido de biblioteca nativa ou falha do SO. Há limpeza Python e tentativas independentes por botão.
- O modo simulado e o probe não validam permissões nem comportamento real do PyAutoGUI neste ambiente. O backend foi verificado com mocks para não interferir no rato do utilizador.
- Sem resultados reais de cliques, arrastamento, scroll, precisão de apontamento ou fadiga. A versão está implementada e validada automaticamente; a aceitação de uso diário continua por demonstrar.

## 7. Próxima validação com webcam

1. Em modo simulado, recolher JSONL com punho parado durante 30 s em várias iluminações/distâncias; quantificar percurso/velocidade residual e perdas.
2. Fazer movimentos lentos/rápidos repetidos, pausas e reposicionamentos; comparar trajetórias e atrasos com um vídeo de referência sincronizado, caso seja necessário medir latência física.
3. Realizar séries de toques, pares de cliques, holds, seleção de texto e arrastamentos; contar falhas e eventos extra, incluindo transições ambíguas.
4. Verificar scroll em ambos os sentidos com movimento horizontal e perdas deliberadas de mão durante hold.
5. Ajustar calibração por utilizador, conferir `Left`/`Right` com o espelhamento escolhido e alinhar `double_ms` ao SO.
6. Repetir em `--live`, com rato físico disponível, e comparar os logs. Só após estes ensaios concluir estabilidade, precisão e usabilidade em webcam real.
