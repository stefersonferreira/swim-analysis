# Changelog

## 0.6.1 — 2026-10-15

Ajustes da simulação de um pedido real (vídeo gravado com a prova já em andamento).

- Sem largada no vídeo: a fase "Nadando" começa na primeira braçada marcada e o painel ao vivo
  aparece; o MP4 termina com o resumo mesmo sem a chegada.
- Ritmo sempre em ciclos/min (no crawl, 1 ciclo = 2 braçadas): o rascunho dizia
  "braçadas/min" para o mesmo número. O número do rascunho é o mesmo do vídeo.
- Observação própria do treinador aparece neutra (não como correção); sem nota duplicada de
  "sem largada"; "braçadas marcadas".

## 0.6.0 — 2026-10-15

Técnica, quadro a quadro (o que a revisão paga escreve à mão, agora com poucos cliques).

- Lista de pontos técnicos por fase e estilo (`swimcv.report.technique`): crawl e peito, cada
  ponto com a frase para o atleta e um exercício; pontos fortes em verde.
- Quadros-chave sugeridos a partir das marcações (por raia); "Usar quadro atual" e "Circular no
  quadro" (recorte ampliado em volta do círculo para o cliente: `frames/{n}.jpg?mx=&my=`).
- Sugestão por IA com visão (`swimcv.report.ai`, opcional, `ANTHROPIC_API_KEY`): escolhe só
  pontos da lista, diz quando não dá para ver; fica pendente até o treinador confirmar.
- Os pontos confirmados entram no rascunho da devolutiva (sem repetir o que os números já
  dizem), no relatório e no link do cliente, com o quadro. Migração 0007.

## 0.5.0 — 2026-10-14

Revisão paga para clientes (no formato do Swimming Everywhere: vídeo curto, análise e
devolutiva de treinador em até 72 h).

- Página pública `/enviar` (celular): instruções de gravação, dados da prova e contato,
  progresso do envio, armadilha contra robôs. `POST /api/public/orders`.
- Link do cliente `/r/{token}`: acompanha recebido → em análise → entregue com o prazo; depois
  de entregue, vídeo, devolutiva, números, relatório e compartilhar no WhatsApp.
- Pedidos (migração 0006): origem, contato, observações, prazo (`SWIM_TURNAROUND_HOURS`), pago,
  situação. A lista vira fila: abertos por prazo, atrasados em vermelho.
- Devolutiva do treinador (resumo, pontos fortes, o que melhorar, exercícios) com rascunho
  gerado só dos números medidos (`swimcv.report.feedback`); entra no relatório e no link.
- "Entregar ao cliente" + mensagem pronta para WhatsApp/e-mail; "Desfazer entrega".
- Senha da área do treinador (`SWIM_ADMIN_PASSWORD`); rotas do cliente seguem públicas.
- Sobreposição: contagem e tempo de ciclo piscam em verde a cada braçada/ciclo marcado.

## 0.4.0 — 2026-10-14

Várias raias no mesmo vídeo (treino com saídas lado a lado).

- Revisão sem teclado: player com botões grandes e barra de posição; vídeo em pé cabe na tela;
  painel "Marcação" com atletas (+ Raia), passo a passo da prova, próximo passo com dica e
  botão "Marcar", correção por "Mudar p/ cá" e "✕". Marcar responde na hora (a tela não espera
  o servidor). "Vídeo e relatório" foi para o painel lateral. Teclas continuam como atalhos.

- Evento com raia (`Event.lane`, schema_version 2; migração 0004). Sem raia = o atleta da
  prova; a largada sem raia vale para todas.
- Revisão: teclas 1–8 escolhem a raia dos próximos eventos (0 volta ao atleta da prova);
  o evento selecionado pode trocar de raia; a raia aparece no quadro e na linha do tempo.
- Quadro comparativo (`swimcv.metrics.compare_lanes`, `/metrics` → `lanes`): saída (apito até
  sair do bloco ou entrar na água), braçadas, ritmo (ciclos/min), tempo, velocidade média e
  distância por ciclo quando há calibração. "–" = não visto no vídeo.
- Sobreposição (tela e MP4): quadro ao vivo por raia (braçadas, ritmo, tempo ao chegar) e
  comparativo lado a lado no fim, com observações de quem revisou (`notes`).
- Sem posições medidas (só largada e chegada), a barra de progresso e a velocidade instantânea
  não aparecem: antes eram interpoladas e pareciam medidas. O resumo mostra ritmo (ciclos/min)
  e velocidade média da prova (distância / tempo).
- `strokes_partial`: ciclos marcados só num trecho do vídeo; o ritmo vale, a contagem vira "–".
  Observações de quem revisou (`notes`) também aparecem no resumo de um atleta.
- Várias raias ao vivo: balão de saída e de chegada de cada raia (quem chega depois mostra a
  diferença), coluna "Saída" no quadro, relógio para na última chegada; comparativo final com
  coluna "Dif.".
- Largada: apito de treino com trinado (o tom desliza entre ~2,5 e 4 kHz) passa a ser
  reconhecido, com o início medido na faixa toda.
- "Ajustes do vídeo final e relatório" na revisão: ciclos marcados só num trecho e observações
  do resumo (`PUT /api/videos/{id}/final-options`, migração 0005).
- Relatório da análise (`/api/videos/{id}/report.html`, botão "Abrir relatório"): resultados,
  pontos para o técnico calculados dos números (de onde vem a diferença), momentos marcados e
  observações; "Salvar em PDF" pelo navegador. Mesmos números do vídeo.
- Correção: "Gerar vídeo" travava quando o desenho de um quadro falhava (o ffmpeg ficava
  esperando quadros); agora o erro aparece. O fim com resumo não exige mais a chegada do
  atleta da prova.

## 0.3.1 — 2026-10-14

Ajustes a partir do primeiro vídeo real de treino (celular em pé, apito, saídas escalonadas).

- Largada: vale o último sinal da sequência de saída (apito longo → apito curto, apitos →
  bipe); gritos no meio da prova ficam de fora. Antes, um treino com apito pegava a voz do técnico.
- Sobreposição em vídeo em pé: painéis 2,2x maiores (tela e MP4), legíveis no celular.
- Sem eventos de nado, a fase "Saída" some após 2 s e o painel e a barra de progresso não
  aparecem (antes mostravam zeros e uma barra parada).

## 0.3.0 — 2026-10-13

Sobreposição com a identidade Fluxi Swim (entrega 12).

- Linha do tempo única (`/api/videos/{id}/overlay.json`): fases, braçadas da piscina atual,
  tempo de ciclo corrente, velocidade, distância percorrida, balões e resumo.
- Sobreposição ao vivo na revisão (tecla V) e modo apresentação em tela cheia.
- "Gerar vídeo": MP4 (H.264 + AAC) com a mesma sobreposição e cartão de resumo no fim,
  gerado no worker com progresso na tela.
- Fontes Fredoka e Nunito (OFL) em `brand/`; navegador e MP4 seguem as mesmas regras
  (teste de paridade entre state.ts e state_at).

## 0.2.0 — 2026-10-13

Análise automática (versão clássica, sem modelo de IA para baixar).

- Largada pelo áudio, logo após o envio.
- Movimento da câmera e calibração propagada para todos os quadros (câmera acompanhando).
- Rastreamento do nadador na própria raia; trajetória e marcador na tela.
- Eventos automáticos: entrada, breakout, braçadas, viradas, chegada, passagens a cada 5 m.
- Reanálise preserva correções manuais; alertas para eventos de baixa confiança.
- Provas sintéticas com verdade conhecida nos testes e no CI.

## 0.1.1 — 2026-10-13

- Só metros: removido todo suporte a jardas (piscina de 25 jd, conversões e rótulos "jd").
  RaceInfo passa a schema_version 2, sem o campo pool_unit; piscinas aceitas: 25 m e 50 m.

## 0.1.0 — 2026-10-13

Etapa 1, entregas 0 a 4: uso próprio com marcação manual de eventos.

- Docker: compose com web, worker (CPU ou GPU NVIDIA), PostgreSQL e Redis; CI que testa,
  constrói as imagens, sobe o compose e roda um teste de navegador; publicação no GHCR.
- Ingestão: proxy todo-intra com os mesmos quadros e tempos do original, tabela de PTS,
  áudio e forma de onda; validação de fps, resolução e duração.
- Métricas: catálogo completo para crawl e peito, com alertas; reproduz os números do
  vídeo de referência.
- Revisão: quadro exato, atalhos de teclado, linha do tempo com áudio, posição por clique,
  métricas ao vivo, histórico de alterações.
- Calibração por cliques com erro por ponto, descarte de clique errado e grade sobreposta.
