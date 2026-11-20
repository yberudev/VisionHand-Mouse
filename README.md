# Invisible Mouse 0.2

Rato relativo por webcam, com processamento local e offline. Começa em modo simulado. O mapeamento experimental atual move com mão aberta e pausa com punho fechado. Os valores iniciais são pontos de partida para calibração, não valores universalmente ideais.

## Instalar e executar

No Windows/PowerShell, na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Force models | Out-Null
if (-not (Test-Path models/hand_landmarker.task)) {
    Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task' -OutFile models/hand_landmarker.task
}
.\.venv\Scripts\python.exe main.py --mirror --diagnostics --log session.jsonl
```

O comando de instalação obtém o modelo oficial Hand Landmarker se ainda não estiver em `models/hand_landmarker.task`. Usa `--model CAMINHO` para apontar para outro ficheiro. Depois da instalação, a aplicação funciona offline.

Após validar os gestos no modo simulado:

```powershell
.\.venv\Scripts\python.exe main.py --mirror --live --diagnostics
```

Se o movimento até aos cantos interromper o experimento com `FailSafeException`, executar com o bloqueio dos cantos desativado:

```powershell
.\.venv\Scripts\python.exe main.py --mirror --live --diagnostics --no-failsafe
```

O failsafe está ativo por padrão; `--no-failsafe` desativa-o apenas nesta execução. Com a janela da pré-visualização em foco, `Espaço` pausa e `Q`/`ESC` encerra. A limpeza e a libertação de botões continuam ativas em ambos os modos.

Foi verificada a integração em Python 3.14.10 / Windows com MediaPipe 0.10.35, OpenCV 4.14.0.94, NumPy 2.5.4 e PyAutoGUI 0.9.54. Noutros ambientes, usar uma versão de Python para a qual estas dependências disponibilizem wheels. Wayland pode exigir outro backend; permissões de acessibilidade e de câmara dependem do SO.

**Windows, em qualquer aplicação no desktop normal: `F8` pausa/retoma e `F9` encerra.** Na janela de pré-visualização: `Q`/`ESC`: sair; `Espaço`: desativar/reativar; `D`: diagnóstico; `S`: guardar configuração; `H`: mostrar/ocultar o esqueleto da mão (visível por padrão). O painel lateral destaca o gesto detetado e apresenta o estado de cada ação, sem tapar a imagem da mão. O failsafe dos cantos está ativo por padrão e pode ser desativado com `--no-failsafe`. A limpeza liberta os botões pertencentes à aplicação mesmo após esse failsafe. Uma falha do próprio backend/SO pode impedir a libertação: a aplicação tenta ambos os botões e propaga o erro.

## Ativar e desativar com dois estalos

Instala as dependências atualizadas e inicia o programa em modo de espera para deixar a câmara livre até ao primeiro par de estalos.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --mirror --live --backend native --no-failsafe --config calibration.fist.json --snap-toggle --start-standby
```

Faz dois estalos com cerca de **140 ms a 1 segundo** de intervalo. Um par abre a câmara e o seguinte liberta a câmara e os botões do rato. Mostra a mão aberta após reativar. O microfone continua ativo em modo de espera e o áudio é processado em memória, sem gravação ou transmissão. Se a câmara estiver ocupada quando tentares reativar, o programa fica em espera para poderes tentar de novo.

Para verificar os estalos separadamente, usa o teste de microfone. O terminal mostra o dispositivo, o nível recebido, o limiar e a confirmação do par. **Ctrl+C** encerra o teste.

```powershell
.\.venv\Scripts\python.exe main.py --snap-test
```

O teste exibe o índice, a interface de captura e os níveis dos canais. No Windows, o programa consulta o estado de silêncio da entrada padrão ou da entrada WASAPI selecionada. Se indicar que está silenciada, verifica o botão de silêncio do microfone em **Definições → Sistema → Som → Entrada**. O volume pode estar acima de zero enquanto a entrada está silenciada.

«Sem sinal útil» indica que chegam amostras, mas o nível ficou perto de zero. Fala normalmente no teste. Se os canais continuarem perto de zero, compara com o medidor do Windows, selecionando o mesmo microfone. Se o Windows captar voz, testa outra entrada com `--microphone N` e usa o mesmo índice ao executar o rato. Se a voz aparecer no teste e os estalos subirem abaixo do limiar, experimenta `--snap-sensitivity 1.5`.

Se o Windows captar voz nesse microfone e a aplicação continuar em zero, compara os modos da entrada WASAPI. Usa o índice marcado como **Windows WASAPI** na lista de dispositivos e fala durante os três testes de três segundos.

```powershell
.\.venv\Scripts\python.exe main.py --snap-test --microphone 9 --microphone-mode compare
```

O modo `raw` solicita ao Windows captura sem processamento adaptativo, quando suportada pelo controlador. `communications` usa a categoria de chamadas. Ambos usam captura partilhada. Se a comparação indicar um modo com sinal, acrescenta o índice e o modo indicados ao comando do rato. Para confirmar os estalos antes disso, usa `--snap-test` com essas mesmas opções. A comparação só mede picos, sem gravar áudio.

**F8** e **Espaço** na janela fazem a mesma alternância. **F9** fecha o programa e liberta também o microfone. Retira `--start-standby` para abrir a câmara logo no arranque. Para escolher outro microfone, lista os dispositivos com `.\.venv\Scripts\python.exe -m sounddevice` e passa o índice com `--microphone N`.

O detetor verifica a duração da energia, a cauda do som e a distribuição das frequências. Os dois impulsos devem ter características semelhantes e um ruído distinto entre eles cancela o par. Se batidas, teclas ou outros ruídos do teu ambiente ainda forem confundidos com estalos, ensina ao programa exemplos dos dois:

```powershell
.\.venv\Scripts\python.exe main.py --snap-calibrate --microphone 9
.\.venv\Scripts\python.exe main.py --snap-test --microphone 9
```

O programa pede cinco estalos isolados, depois exemplos de ruídos que deve ignorar. Usa o mesmo microfone, modo e posição em que pretendes usar o rato. A calibração e o teste deixam a câmara livre. O ficheiro local `snap-calibration.json` contém apenas características numéricas dos sons e é carregado automaticamente por `--snap-test` e `--snap-toggle`. Para reutilizar um perfil noutro caminho, usa `--snap-profile CAMINHO` nos comandos. Sons acusticamente muito parecidos ainda podem exigir nova calibração.

## Gestos

| Gesto | Ação |
|---|---|
| Mão aberta | Movimento relativo |
| Polegar recolhido + quatro dedos estendidos, depois mão aberta | Clique esquerdo (imagem «Clicke esquerdo») |
| Dois toques rápidos do gesto esquerdo | Dois cliques normais, interpretados pelo SO |
| Gesto esquerdo mantido ou com deslocamento deliberado | Pressionar esquerdo e arrastar |
| Indicador recolhido + polegar e restantes três dedos estendidos, depois mão aberta | Clique direito (imagem «Clicke direito») |
| Gesto direito mantido | Manter direito pressionado e permitir movimento |
| Polegar e indicador unidos em «OK» + restantes três dedos estendidos | Scroll vertical; cursor suspenso (imagem «Scroll cime e baixo») |
| Punho fechado | Pausar e reposicionar |
| Desconhecido | Cancelar com segurança; nunca equivale ao gesto de movimento |

É necessário começar com mão aberta estável e voltar a fazê-lo após pausa/perda. Para terminar um toque ou arrastamento e continuar a mover, regressar à mão aberta. Fechar o punho cancela o toque pendente sem clique e liberta qualquer botão mantido. A intenção tem de permanecer estável durante `gesture_ms`. Punho fechado, perda de mão e desativação libertam imediatamente. Durante um clique pendente/hold, um gesto desconhecido válido congela o movimento durante até `uncertain_ms`; se não recuperar, cancela sem clique e liberta o botão. O tempo incerto não conta para ativar hold. Nos restantes estados, desconhecido cancela imediatamente. O scroll termina no primeiro frame sem o sinal «OK», respeitando a histerese da distância entre pontas. Um toque entre `tap_ms` e `drag_ms`, sem deslocamento suficiente, é cancelado deliberadamente: não produz clique nem hold.

O duplo clique emite **exatamente dois cliques simples**, sem chamada adicional a `doubleClick`. `double_ms` controla o agrupamento reconhecido pelo motor e mostrado no diagnóstico; o intervalo e a tolerância espacial efetivos continuam a ser os do SO. Ajustar a configuração e a cadência aos valores do sistema. A aplicação não altera as definições globais do rato.

## Calibração persistente

```powershell
# Editor de terminal: Enter mantém cada valor, guarda e termina.
.\.venv\Scripts\python.exe main.py --calibrate
# Alterações pontuais persistentes e execução simulada:
.\.venv\Scripts\python.exe main.py --mirror --set sensitivity=1.4 --set deadzone=0.015 --save-config
# Ficheiro alternativo:
.\.venv\Scripts\python.exe main.py --config perfil.json --calibrate
```

`calibration.json` é carregado automaticamente, se existir. A gravação substitui atomicamente um ficheiro temporário após validação. `calibration.example.json` contém todos os valores iniciais. Aumentar `min_cutoff` reduz suavização/atraso; aumentar `beta` abre o filtro mais depressa em movimento. Reduzir `min_cutoff` aumenta suavização. Configurações inválidas falham antes de ativar a câmara.

| Parâmetro | Inicial | Significado |
|---|---:|---|
| sensitivity | 1.7 | Ganho proporcional |
| acceleration | 0.35 | Ganho progressivo com velocidade, saturado a 4 larguras/s |
| min_cutoff / beta | 1.8 / 0.7 | Filtro One Euro; derivada filtrada a 1 Hz |
| deadzone | 0.012 | Larguras de palma; adaptação até 1.5 vezes este valor |
| pixels_per_unit | 120 | Conversão final para pixels com acumulação fracionária |
| tap_ms / double_ms | 450 / 400 | Toque e agrupamento de pares de cliques |
| drag_ms / drag_distance | 650 / 0.18 | Hold por duração confirmada, ou distância depois da janela de toque |
| drag_confirm_ms | 100 | Tempo de deslocamento sustentado após a janela do toque |
| uncertain_ms | 180 | Máximo de incerteza com movimento congelado antes de cancelar/libertar |
| min_palm_scale / max_palm_scale | 0.07 / 0.70 | Faixa de tamanho da palma para controlo; fora dela pede aproximar/afastar |
| scale_smoothing_ms | 250 | Constante temporal para estabilizar a escala do movimento |
| scroll_gain / scroll_deadzone | 9 / 0.025 | Passos por largura de palma; limiar vertical |
| pinch_distance / pinch_release | 0.30 / 0.42 | Distância entre pontas do polegar/indicador em larguras de palma; entrar/sair do scroll OK |
| gesture_ms / recover_ms | 45 / 150 | Estabilização e recuperação com o gesto de movimento |
| move_gesture | OPEN | `OPEN`: aberta move, fechada pausa; `FIST`: mapeamento original |
| max_gap_ms | 250 | Timeout de amostras e rejeição de frames antigos |
| max_speed / max_step | 12 / 0.6 | Rejeitar velocidade anormal; limitar percurso por atualização antes do ganho |
| dominant_hand | any | `any`, `Left` ou `Right`, conforme o rótulo do modelo na imagem apresentada |

Validar o rótulo da mão ao mudar `--mirror`; não existe identidade persistente de pessoas. A troca do rótulo de mão força recuperação segura. A orientação geométrica é independente de esquerda/direita e de rotações no plano. A normalização corrige o aspeto da imagem e usa distâncias 3D dos landmarks.

## Arquitetura

- `capture.py`: thread de captura com um único frame recente, sem fila crescente.
- `gestures.py`: ângulos PIP/DIP/polegar, alcance radial, abertura normalizada, pinça OK prioritária sobre clique direito, validade da palma, histerese e confirmação temporal.
- `motion.py`: deltas do centro da palma divididos pela escala média entre amostras; One Euro, rejeição de outliers, dead zone acumulativa e aceleração por velocidade temporal.
- `engine.py`: máquina determinística com MOVE, LEFT_PENDING, LEFT_DRAG, RIGHT_PENDING, RIGHT_HOLD, SCROLL, IDLE e LOST_HAND.
- `controller.py`: recuperação, mão dominante, confiança, pausas, estabilização e coordenação.
- `backends.py`: simulação, seleção de backend, propriedade de botões e preservação de frações de pixel.
- `wininput.py`: backend nativo Windows por SendInput, com verificação de aceitação, DPI e coordenadas do desktop virtual (incluindo monitores com origem negativa).
- `window.py`: pré-visualização num processo isolado, com um único frame em espera; mover/redimensionar a própria janela não bloqueia a inferência ou os eventos de entrada.
- `hotkeys.py`: consulta apenas F8/F9 no Windows, sem recolher texto digitado nem instalar hooks.
- `config.py`, `diagnostics.py`, `main.py`: persistência, métricas e interface.

Durante intenção de clique não se emitem movimentos. Deslocamento durante a janela de toque nunca ativa hold: depois dessa janela, é necessária distância sustentada durante `drag_confirm_ms`, ou atingir `drag_ms` de evidência confirmada. Ao confirmar arrastamento, o motor aplica o deslocamento pendente, limitado por atualização; não o descarta. O gesto de pausa (punho por padrão), perda e desativação cancelam pendências sem gerar clique. Incertezas geométricas breves em pending/hold congelam o movimento; exceder a tolerância também cancela sem clique. A retomada ancora a posição atual. Outliers de velocidade/escala cancelam o rastreamento e exigem recuperação, em vez de mover o cursor com dados suspeitos.

## Diagnóstico

`--diagnostics` mostra FPS de captura e de processamento, tempo de captura, pré-processamento, inferência, controlo, emissão, idade do frame, gesto, estado, centro bruto, posição relativa filtrada, velocidade, certeza geométrica, estabilidade, duração, perdas e últimos eventos. `--log session.jsonl` grava os mesmos valores por frame, sem imagens. Inclui ainda motivo de pausa/perda (`reason`), backend, aceitação dos eventos, contador de envios e PID da aplicação em primeiro plano (sem títulos nem conteúdo). Erros de execução geram uma linha final de tipo `error`. O ficheiro indicado é substituído a cada execução.

Os tempos são estimativas de relógio monotónico: captura inclui espera no driver; idade começa após `read()`; não incluem a exposição do sensor, atualização física do ecrã nem toda a latência do SO. FPS de inferência é o débito do ciclo que executa inferência. A certeza geométrica é binária (regra suportada ou desconhecida), **não** uma probabilidade calibrada; o score de handedness do modelo é um filtro adicional, não confiança de cada landmark. Logs crescem enquanto a sessão estiver aberta.

## Validação reproduzível

```powershell
python -m unittest discover -s tests -v
python tools/benchmark.py
.\.venv\Scripts\python.exe tools/smoke_test.py
# Opcional: cinco frames de câmara; não guarda imagens nem emite eventos.
.\.venv\Scripts\python.exe tools/smoke_test.py --camera 0
```

Os testes puros não precisam de OpenCV, MediaPipe nem PyAutoGUI. As fixtures geram 21 landmarks com articulações, rotação, espelhamento, escala e timestamps controlados. O benchmark conserva o motor original em `tests/baseline_engine.py` e usa seed fixa. O relatório de auditoria, resultados e limitações está em `VALIDATION.md`.

## Limitações e validação manual necessária

Não foi validada a usabilidade diária, precisão de apontamento nem taxa de falsos cliques com utilizadores. A leitura breve da webcam neste ambiente não continha mãos. Testes sintéticos não reproduzem oclusão, iluminação variável, movimentos fora do plano, mãos parcialmente visíveis ou erros reais do MediaPipe. A compensação de escala elimina a divisão de coordenadas absolutas; não consegue separar completamente translação de deformação/perspetiva da palma. O centro usa punho e quatro MCP, não pontas dos dedos.

A política conservadora interrompe o arrastamento quando a geometria fica desconhecida por mais de `uncertain_ms`. Durante essa tolerância o botão permanece pressionado, mas não há movimento; punho fechado ou perda real continuam a libertar imediatamente. Não existe um watchdog externo: bloqueio indefinido numa chamada nativa ou encerramento forçado do processo não garantem limpeza em Python. A captura é uma thread daemon e tenta terminar com timeout; um driver bloqueado pode não terminar até o processo sair.

Antes de uso diário: calibrar mão/iluminação, comparar ruído parado e movimentos lentos/rápidos em sessões repetidas, testar selecionar texto e arrastar ficheiros, medir cliques/dobros/scroll e provocar perda de mão durante hold. Começar no modo simulado e só depois repetir com `--live`. Conservar o rato físico disponível.

Para comparar com o mapeamento anterior, executar com `--set move_gesture=FIST`. Para persistir a escolha, acrescentar `--save-config`. O painel de gestos adapta-se ao mapeamento escolhido.

Os IDs de diagnóstico dos comandos são `LEFT`, `RIGHT` e `SCROLL`. Os antigos gestos de indicador isolado, indicador + médio e polegar isolado passam a desconhecidos. Os nomes das três imagens fornecidas determinam o novo mapeamento; a alteração de `move_gesture` só troca mover/pausar, não repõe os gestos antigos de clique/scroll.

## Arrastamento da própria janela e controlo noutras aplicações

No Windows, a pré-visualização corre num processo separado. O processamento da webcam e a emissão de eventos continuam no processo de controlo, mesmo durante o ciclo modal de mover/redimensionar a janela. A fila de pré-visualização descarta frames; o controlo nunca espera que a janela termine uma operação modal. Fechar a janela encerra o controlo e liberta os botões pertencentes à aplicação.

O backend padrão (`--backend auto`) usa SendInput no Windows e PyAutoGUI nos restantes sistemas. Para comparar com o backend anterior, usar `--backend pyautogui`. O backend nativo verifica o número de eventos aceites; a aceitação não garante que todas as aplicações respondam ao evento. Falhas explícitas interrompem a execução e são registadas em `--log`, seguidas da tentativa de libertação dos botões.

```powershell
.\.venv\Scripts\python.exe main.py --mirror --live --backend native --diagnostics --no-failsafe --set move_gesture=OPEN --log session-live.jsonl
# Para isolar completamente a janela durante um ensaio:
.\.venv\Scripts\python.exe main.py --mirror --live --backend native --no-preview --no-failsafe --log session-headless.jsonl
```

No modo sem pré-visualização, usar F8/F9 no Windows ou Ctrl+C no terminal. As teclas globais são consultadas a cada ciclo: não constituem um watchdog para um bloqueio indefinido da inferência. Mantêm-se as limitações do desktop seguro e de aplicações que interceptam teclas.

O Windows restringe a injeção em aplicações com nível de integridade superior. Se o destino estiver como administrador, o controlador sem privilégios equivalentes pode não conseguir atuar. O projeto não eleva privilégios automaticamente e não contorna o UAC/desktop seguro. Referências: [ciclo modal de mover/redimensionar](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-entersizemove), [SendInput e UIPI](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput), [GetAsyncKeyState](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getasynckeystate).

Ferramentas de verificação: `tools/smoke_app.py` processa cinco frames reais com pré-visualização simulada, sem backend real; `tools/smoke_desktop.py` apresenta um frame de teste num processo real e envia **um evento nativo de movimento para a posição atual**, sem clicar, manter botões ou fazer scroll. Os testes unitários de input nativo usam uma API simulada. A validação de arrastamento real e de aplicações específicas continua a exigir ensaio manual.

## Perfil para separar toque e botão mantido

O perfil `calibration.precise.json` contém um ponto de partida mais conservador: toque até 450 ms e hold após 650 ms de evidência confirmada. A distância não ativa hold durante o toque e precisa de 100 ms de confirmação depois dele. A janela intermédia continua a cancelar gestos ambíguos. O painel mostra o progresso do pending até ao limiar de hold. Quando mostrar «Arrastar: esquerdo premido», o botão já foi enviado ao backend.

```powershell
.\.venv\Scripts\python.exe main.py --mirror --live --backend native --no-failsafe --diagnostics --config calibration.precise.json --log session-calibration.jsonl
python tools/analyze_session.py session-calibration.jsonl
```

O perfil pode ser editado pelo editor `--calibrate --config calibration.precise.json` ou por `--set NOME=VALOR --save-config`. Estes valores não foram calibrados pessoalmente com a mão do utilizador. Aumentar `tap_ms` exige manter `drag_ms` acima dele; reduzir muito `uncertain_ms` pode voltar a interromper drags, aumentá-lo mantém o botão pressionado mais tempo quando a pose é incerta.

O movimento usa a mediana de três dimensões da palma e escala suavizada no tempo. Os gestos continuam a usar a sua escala geométrica sem suavização. Quando a palma é demasiado pequena/grande para a faixa configurada, não se amplifica o movimento: o controlo para e o painel pede aproximar/afastar. A escala é uma medida relativa da imagem, não distância em metros. Este método não elimina perspetiva, oclusão ou toda a perda de precisão com a mão longe.

O JSONL inclui `palm_scale`, `filtered_scale`, `activation` (duração ou distância deliberada), limiares de toque/hold e `uncertainty_ms`. O analisador resume o que foi observado; sem rótulos do utilizador não calcula uma taxa de falsos cliques. Para a próxima sessão, comparar 20 toques curtos e 10 holds/arrastamentos e anotar quais eram intencionais; repetir numa posição próxima, média e distante dentro da faixa indicada.

## Mira verde no cursor (Windows e Linux X11)

No modo `--live`, uma mira estilo HUD acompanha o cursor no desktop: caixa de 64 × 64 pixels com o ponto do cursor no centro, cantos reforçados e quatro linhas-guia verdes até às bordas do desktop virtual. O cursor normal continua visível. A mira aparece quando o controlo por gestos está ativo; pausa, perda real ou recuperação escondem-na. Confirmações de gesto e a breve tolerância de incerteza mantêm a mira estável enquanto o controlo continua armado. Ao chegar à borda, a caixa é recortada pelo ecrã, mantendo o cursor no centro geométrico.

No Windows, a sobreposição usa uma janela nativa layered/transparent/no-activate. No Linux/X11, usa uma janela ARGB transparente e uma região de entrada vazia (ShapeInput), para que o rato continue a interagir com as aplicações por baixo. Ambas ficam sem foco, não injetam eventos de entrada e correm num processo separado; o controlador só publica estado e heartbeat. No Linux, a sessão precisa de compositor com extensões RENDER e SHAPE 1.1. Se faltar heartbeat durante cerca de 400 ms (ou o timeout de rastreamento configurado, se superior), a mira desaparece. Uma falha detetada no processo visual desativa a mira e mantém o motor de controlo.

```powershell
.\.venv\Scripts\python.exe main.py --mirror --live --backend native --no-failsafe --diagnostics --config calibration.precise.json
# Mesmo comando sem a mira:
.\.venv\Scripts\python.exe main.py --mirror --live --backend native --no-failsafe --config calibration.precise.json --no-hud
```

A mira funciona também com `--no-preview` e fica ativa por padrão em `--live`; `--no-hud` desativa-a. Está desativada no modo simulado, fora do Windows/Linux X11 e em Wayland nativo. No Windows, não aparece sobre o desktop seguro do UAC; em ambos os sistemas, aplicações em modo exclusivo podem ocultar sobreposições de desktop.

Validação visual/nativa sem webcam, cliques ou movimentos: `.\.venv\Scripts\python.exe tools/smoke_hud.py`. A ferramenta mostra a mira brevemente e verifica cor na borda da caixa, estilos, hit-test transparente, preservação do foco, ocultação na pausa e por heartbeat expirado. O teste de hit-test não equivale a uma série de cliques/arrastamentos com utilizador. Referência da transparência: [janelas layered/transparent do Windows](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features).

### Mira após minimizar ou mudar de aplicação

A mira é criada explicitamente como topmost e verifica a própria visibilidade real. Enquanto o controlo está ativo, repõe a visibilidade e a ordem de sobreposição sem ativar a janela, incluindo após uma ocultação/minimização externa. Transições breves de gesto deixam de a fazer piscar. Minimizar a pré-visualização não é tratado como fechar: no Windows, o processo verifica a existência do HWND e deixa de repintar a imagem enquanto está minimizada. O rastreamento, a mira e as teclas F8/F9 continuam independentes dessa janela. Fechar explicitamente a pré-visualização continua a encerrar o controlo.

O JSONL passou a incluir `hud` com visibilidade solicitada/observada, estado do processo, idade do heartbeat, recuperações e erro. Isso permite distinguir uma ocultação visual de uma paragem segura por perda/pausa do gesto. Para guardar uma nova sessão sem substituir a anterior, acrescentar `--log session-hud.jsonl` ao comando de execução.

Teste nativo reproduzível: `.\.venv\Scripts\python.exe tools/smoke_minimize.py`. Cria apenas as suas próprias janelas (selecionadas por PID), verifica três ciclos de minimizar/restaurar, ocultação e minimização forçada da mira, recuperação de z-order, pixels verdes, ausência de roubo de foco, continuidade da pré-visualização e encerramento explícito. Não usa webcam nem injeta eventos de rato. A reposição de ordem usa [SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos) com `SWP_NOACTIVATE`.

## Experimento: clique esquerdo com punho fechado

Acrescentar `--fist-click` ativa o mapeamento experimental apenas nesta execução (sem `--save-config`). Mão aberta continua a mover; fechar e voltar a abrir rapidamente produz um clique esquerdo; manter o punho fechado ativa hold/arrastamento conforme os limiares de calibração. Abrir a mão liberta o botão. Clique direito, scroll OK e mira mantêm-se.

```powershell
.\.venv\Scripts\python.exe main.py --mirror --live --backend native --no-failsafe --diagnostics --config calibration.precise.json --fist-click
```

Como o punho passa a clicar, o gesto de **polegar recolhido e quatro dedos estendidos** passa a pausar neste modo. A pausa substituta é confirmada por `fist_pause_ms` (350 ms iniciais no modo de clique com punho), para não confundir uma etapa breve de fechar/abrir a mão com uma pausa intencional. O movimento congela durante essa confirmação. Uma breve pose desconhecida durante a formação do punho pode recuperar dentro de `uncertain_ms`; perder a mão ou desativar continua a libertar imediatamente. F8 pausa/retoma e F9 encerra independentemente desses gestos no desktop normal do Windows.

O painel identifica «Esquerdo: punho fechado» e «Pausa: polegar recolhido». Os logs incluem `left_click_gesture` e `pause_gesture`. Para persistir, usar `--fist-click --save-config`; o campo guardado é `left_click_gesture: "FIST"`. Para voltar ao clique anterior, remover a flag (se não foi gravado) ou usar `--set left_click_gesture=LEFT --save-config`. Movimento e clique não podem usar simultaneamente o punho: essa configuração é rejeitada antes da câmara.

### Quando o punho aparece como desconhecido

O punho usa uma regra própria: quatro dedos com evidência de flexão e pontas compactas junto à palma, mais polegar próximo da palma. Não exige que as articulações do polegar correspondam a uma única posição recolhida. Dedos arredondados na banda ambígua de ângulos precisam de evidência adicional de compactação (relação entre a distância MCP–ponta e o comprimento dos segmentos); dedos estendidos, cadeias de landmarks colapsadas e polegar claramente levantado não são promovidos a punho.

Em `--diagnostics` aparece `fist fingers N/4 | thumb compact True/False`. O JSONL inclui `geometry` com estados dos dedos, ângulos, alcance, distâncias normalizadas à palma e evidência de compactação do polegar. Não são probabilidades calibradas. Se continuar UNKNOWN, estes valores permitem identificar a condição que falhou; a imagem ou uma sessão de landmarks reais ainda pode ser necessária para ajustar poses/oclusões específicas. Para uma sessão separada, acrescentar `--log session-fist.jsonl` ao comando com `--fist-click`.

## Clique simples por ciclo rápido da mão

O modo `--fist-click` tem agora um detetor temporal próprio: **mão aberta → fechar brevemente → voltar a abrir** produz exatamente um clique na reabertura. Não é necessário manter a pose fechada até ao limiar de arrastamento. Cada extremidade precisa de pelo menos duas amostras e `fist_press_ms`/`fist_release_ms` (20 ms iniciais); a latência real depende do FPS. Um único frame fechado não clica. A reabertura usa os quatro dedos estendidos, sem exigir que o polegar já esteja totalmente aberto. O gesto direito e o sinal OK não são tratados como reabertura.

`calibration.fist.json` é um perfil inicial para este teste, com ciclo de clique até `fist_tap_ms=600` ms e hold por duração confirmada em `drag_ms=750` ms. Distância só pode antecipar hold depois da janela do toque e da confirmação de deslocamento, nunca durante o toque. Terminar um hold gera apenas libertação, sem clique adicional. O ciclo tem limite de tempo real para que uma longa sequência incerta não seja contada como um toque curto.

O gesto de polegar recolhido com quatro dedos estendidos completa primeiro a reabertura de um clique/hold; se permanecer nessa pose no estado de movimento, pausa após `fist_pause_ms=350` ms. Isso evita cancelar a abertura natural da mão. F8 continua a pausar imediatamente, e perda real da mão/desativação continuam a cancelar sem clique e a libertar botões.

O punho usa agora escala de palma robusta, tolera maior variação do polegar próximo e pode ser mantido através de um dedo geometricamente incerto, desde que não esteja estendido nem degenerado. A aquisição continua a exigir evidência dos quatro dedos: um deles pode estar um pouco fora da região compacta se apresentar flexão e alcance claramente recolhidos. Não se promove um gesto arbitrário desconhecido a punho.

```powershell
.\.venv\Scripts\python.exe main.py --mirror --live --backend native --no-failsafe --diagnostics --config calibration.fist.json --fist-click --record-landmarks --log session-pulse.jsonl
# Repetir o controlo sobre a gravação, sem webcam nem input real:
python tools/replay_landmarks.py session-pulse.jsonl --config calibration.fist.json
```

`--record-landmarks` é opcional e requer `--log`: guarda as coordenadas na imagem e em 3D quando disponíveis, além do aspeto, rótulo da mão e score utilizados. A gravação é local e não inclui imagens. O replay usa os mesmos timestamps e pode comparar eventos ao alterar um perfil. Logs antigos sem landmarks não permitem essa reprodução e não são convertidos por estimativa. A comparação não identifica intenção do utilizador por si só: é preciso anotar quais tentativas eram cliques ou holds.

O painel mostra «Abrir: clique | manter …» durante o pending. O JSONL regista também a fase/amostras do detetor de ciclo e o tempo desde o fecho. Os limiares são um ponto de partida, ainda não uma calibração individual concluída.

### Mão inclinada e visualização à distância

O reconhecimento usa os pontos da imagem como fonte principal. Quando a projeção da palma fica muito estreita ou inválida, o classificador consulta os pontos 3D do MediaPipe. Se o 3D indicar um gesto desconhecido e a imagem reconhecer um gesto, prevalece a imagem. A posição do cursor e o tamanho aparente da mão vêm dos pontos da imagem. O diagnóstico indica a fonte usada (`world` ou `image`), e sessões com `--record-landmarks` permitem repetir as duas fontes no replay.

Quando a mão detetada ocupa pouco espaço, a pré-visualização mostra um recorte ampliado com o esqueleto redesenhado e contornado. O recorte aparece no lado oposto da mão e a tecla **H** alterna ambas as vistas do esqueleto. A ampliação é visual. O alcance de deteção continua a depender dos detalhes que a câmara capta.
