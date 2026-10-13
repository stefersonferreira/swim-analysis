# Changelog

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
