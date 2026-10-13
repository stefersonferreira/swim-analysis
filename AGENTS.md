# Regras para agentes de IA (e pessoas) neste repositório

Leia antes de mudar qualquer coisa. A especificação completa está ligada em `spec/README.md`;
a ordem de construção e os critérios de pronto estão lá e na tabela abaixo.

## Regras

1. Leia a spec e o contrato do módulo (`pipeline/swimcv/contracts/`) antes de mexer nele.
2. Uma entrega por vez. Só comece a próxima quando a anterior cumprir o critério de pronto.
3. Só metros e segundos, por dentro e na tela. Piscinas de 25 m ou 50 m. **Tempo sempre pelo PTS** da tabela de quadros
   (`frames.parquet`), nunca por `índice / fps`: vídeos de celular têm taxa variável.
4. Métricas são funções puras (`swimcv/metrics/compute.py`): sem arquivo, banco ou relógio.
5. Mudou um contrato? Suba `schema_version`, rode `uv run python tools/export_schemas.py`
   e commite `spec/schemas/`. O CI falha se o esquema exportado não bater.
6. Tudo roda dentro do Docker e está documentado no README. Nada instalado no Windows além do
   Docker Desktop. Scripts `.sh` com final de linha LF (`.gitattributes` cuida disso).
7. Nenhuma dependência GPL ou AGPL (o CI verifica Python e npm). LGPL dinâmica é aceita
   (psycopg). ffmpeg é chamado como programa externo, nunca ligado ao código. Detector: RT-DETR
   (Apache 2.0), **não** Ultralytics YOLO (AGPL).
8. Nenhuma chave ou segredo no código: só no `.env` (fora do git).
9. Antes de cada commit: `uv run ruff check . && uv run ruff format --check . && uv run pytest`
   e, no front-end, `npx tsc -b`. Uma mudança que piore um teste golden além da tolerância não entra.
10. GPU de referência: RTX 500 Ada com 4 GB. Até 3,5 GB de memória de vídeo: modelos em FP16,
    carregados um de cada vez.
11. Nunca apague eventos de verdade: `deleted = true` e registro no `audit_log` (vira dado de
    treino e mede a precisão do automático).
12. Ao terminar uma entrega: atualize README, CHANGELOG e marque a entrega na tabela abaixo.

## Entregas (etapa 1)

| # | Entrega | Pronto quando | Estado |
| --- | --- | --- | --- |
| 0 | Esqueleto: compose, web, worker, db, redis, healthchecks, GPU | Máquina limpa sobe com um comando; worker GPU vê a RTX 500 | Feito (validar no notebook) |
| 1 | Ingestão | PTS crescente; proxy com o mesmo número de quadros; taxa variável tratada | Feito |
| 2 | Biblioteca de métricas | Catálogo inteiro testado, incluindo o vídeo de referência e o peito | Feito |
| 3 | Player de revisão e linha do tempo | Quadro mostrado = quadro pedido; marcação manual com atalhos | Feito |
| 4 | Calibração por cliques (câmera parada) | Erro de reprojeção ≤ 0,15 m em 5 vídeos de 25 m | Feito (falta medir em 5 vídeos reais) |
| 5 | Movimento da câmera e propagação | Deriva ≤ 0,3 m ao longo de uma piscina | |
| 6 | Detecção (RT-DETR), rastreamento, seleção | Nadador certo do início ao fim nos vídeos de referência | |
| 7 | Trajetória | Passagem nos 15 m a ±0,15 s do anotado | |
| 8 | Áudio da largada e eventos de fase | Metas do automático para reação, breakout e viradas | |
| 9 | Braçadas no crawl | Exata em 85% das piscinas do treino | |
| 10 | Braçadas no peito | Exata em 85% das piscinas do treino | |
| 11 | Alertas e recálculo ao corrigir | Corrigir um evento atualiza as métricas em < 1 s | Parcial (recálculo e alertas básicos feitos) |
| 12 | Vídeo com sobreposição | Prova de referência renderizada com todos os elementos | |
| 13 | Relatório web e PDF | PDF idêntico à página, gerado no contêiner | |
| 14 | Rascunho de feedback por IA | Rascunho no modelo de seções, só com métricas aprovadas | |
| 15 | Validação | Critérios de aceite no conjunto de teste | |

## Mapa do código

```
pipeline/swimcv/contracts/    modelos de dados trocados entre módulos (fonte da verdade)
pipeline/swimcv/ingest/       módulo 1: proxy todo-intra, tabela de PTS, áudio, leitura de quadro
pipeline/swimcv/calibration/  calibração por cliques (homografia imagem -> piscina)
pipeline/swimcv/metrics/      catálogo de métricas (puro) + resolução de posição + unidades
pipeline/swimcv/storage/      caminhos por vídeo (pasta local; S3 na etapa 2)
backend/app/                  FastAPI, banco (SQLAlchemy + Alembic), worker Celery
frontend/src/                 React + Vite: lista, upload, revisão, calibração
tests/                        unit, integration (PostgreSQL), e2e (navegador), golden
```

## Armadilhas conhecidas

- O proxy precisa manter a base de tempo do original (`passthrough_args` em `ingest/run.py`);
  sem isso o encoder arredonda os tempos e a taxa variável some.
- A imagem `worker-gpu` usa Ubuntu 22.04 (ffmpeg 4.4); a `worker`, Debian 12 (ffmpeg 5.1).
  As opções do ffmpeg são escolhidas pela versão em tempo de execução.
- Na tela de revisão, alterações de eventos passam por uma fila: nunca troque por chamadas
  paralelas, ou um clique rápido pode ir para o evento errado.
