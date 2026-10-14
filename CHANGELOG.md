# Changelog

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
