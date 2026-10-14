# Análise de Provas de Natação

Ferramenta para medir provas de natação a partir de um vídeo de celular: reação, 15 m,
breakout, braçadas, tempo de ciclo, velocidade, distância por ciclo, viradas e parciais.
Estilos da v1: livre (crawl) e peito; piscinas de 25 m e 50 m. Tudo em metros.

**Estado atual:** você envia o vídeo (com a raia do nadador) e calibra a piscina com alguns
cliques. A partir daí a análise é automática: largada pelo som, posição do nadador quadro a
quadro (com câmera parada ou acompanhando), entrada, breakout, braçadas, viradas, chegada e
passagens a cada 5 m. Você só confere e corrige na tela de revisão; as métricas recalculam na
hora. Ainda manual: pés fora do bloco (para a reação).

A especificação completa está no documento da spec (link em [`spec/README.md`](spec/README.md)).

## Instalação (Windows com Docker Desktop)

Só precisa do **Docker Desktop** (com WSL2) e do **git**. Nada de Python, Node ou ffmpeg.

1. **Placa NVIDIA (opcional, recomendado):** mantenha o driver NVIDIA atualizado no Windows.
   Confira que o Docker enxerga a placa:
   ```
   docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
   ```
2. **Memória do WSL2:** crie `C:\Users\<você>\.wslconfig` com:
   ```ini
   [wsl2]
   memory=16GB
   processors=16
   ```
   Depois rode `wsl --shutdown` no PowerShell e reabra o Docker Desktop.
3. **Clone dentro do WSL** (não em `C:\`, que é lento para o Docker). No terminal do Ubuntu (WSL):
   ```bash
   git clone https://github.com/stefersonferreira/swim-analysis.git
   cd swim-analysis
   cp .env.example .env        # COMPOSE_PROFILES=gpu (NVIDIA) ou cpu
   docker compose up -d --build
   ```
   A primeira vez compila as imagens (alguns minutos). Depois, `docker compose up -d` sobe em segundos.
4. Abra **http://localhost:8080**.

Sem placa NVIDIA, troque para `COMPOSE_PROFILES=cpu` no `.env`.

Quando as imagens publicadas pelo CI estiverem acessíveis (pacotes do GitHub), dá para baixar
prontas em vez de compilar: `docker compose pull && docker compose up -d`.

### Comandos úteis

| O que | Comando |
| --- | --- |
| Subir / parar | `docker compose up -d` / `docker compose down` |
| Ver logs | `docker compose logs -f web worker-gpu` |
| Atualizar | `git pull && docker compose up -d --build` |
| Worker vê a GPU? | `curl localhost:8080/api/system/worker` |
| Backup do banco | `docker compose exec db pg_dump -U swim swim > backup.sql` |
| Reprocessar um vídeo | botão na API: `POST /api/videos/<id>/reingest` |

Vídeos e resultados ficam em `./data`; o banco, no volume `pgdata`.

## Como usar

1. **Enviar vídeo:** estilo, distância, piscina, raia e, se tiver, tempo final e parciais oficiais.
2. **Calibração** (aba): crie uma âncora no quadro atual e clique pontos de posição conhecida —
   onde cada corda encontra a parede (0 m), as marcas de 5 m e 15 m e a parede oposta. Com
   câmera parada, uma âncora com 4 a 8 pontos basta. Aceita com erro médio até 15 cm.
3. **Análise automática:** roda sozinha ao salvar a calibração (precisa da raia nos dados da
   prova) e aparece na barra "Análise automática". O marcador rosa mostra onde o sistema acha
   que está a cabeça do nadador; eventos automáticos aparecem mais claros na linha do tempo.
4. **Revisão** (aba): tudo por clique. Use os botões do player (−1 s, quadro a quadro,
   velocidades ¼× e ½×) ou arraste a barra até o momento certo. O painel **Marcação** mostra o
   passo a passo da prova (apito, saída do bloco, entrada, ciclos, viradas, toque) e o próximo
   que falta, com a dica de qual quadro escolher: toque em "Marcar" e ele é registrado no quadro
   atual. Para corrigir, toque no horário do momento, ajuste o quadro e use "Mudar p/ cá"; "✕"
   apaga. Vários atletas no vídeo: "+ Raia" para cada um e marque um de cada vez. O que você
   corrige nunca é sobrescrito por uma nova análise.
5. **Sobreposição e vídeo:** durante a reprodução aparecem relógio de prova, fase, braçadas,
   tempo de ciclo, velocidade, balões que seguem o nadador (breakout, 15 m, parciais, chegada)
   e a barra de progresso. "Modo apresentação" abre em tela cheia sem as marcações de edição.
   "Gerar vídeo" grava um MP4 com o mesmo visual e um resumo no fim, para enviar ao atleta.
6. **Várias raias no mesmo vídeo:** marque a largada uma vez (vale para todas) e use as teclas
   1–8 para dizer de que raia são as entradas, braçadas e chegadas. A sobreposição troca o
   painel do atleta por um quadro com braçadas, ritmo e tempo de cada raia e, no fim, mostra
   o comparativo: saída, braçadas, ritmo, tempo e velocidade média.
7. **Ajustes do vídeo final e relatório:** se os ciclos foram marcados só num trecho (o nadador
   sai de quadro), marque a opção e a contagem aparece como "–" (o ritmo continua valendo).
   Escreva observações, uma por linha, que entram no resumo do vídeo e no relatório. "Abrir
   relatório" mostra resultados, pontos para o técnico e momentos marcados; "Salvar em PDF"
   gera o arquivo. Depois de mudar, gere o vídeo de novo.

Atalhos de teclado (opcionais, para quem preferir):

| Tecla | Ação |
| --- | --- |
| ← / → (Shift: ±10) | Quadro anterior / próximo |
| K ou espaço · L · J | Pausar · reproduzir (repetir acelera) · voltar devagar |
| I · O · E | Sinal de largada · pés fora do bloco · entrada na água |
| B · S | Breakout · braçada (crawl: cada braço; peito: cada ciclo) |
| H · W · F | Toque das mãos (peito) · pés na parede · toque final |
| P | Passagem pela marca escolhida no painel |
| [ / ] | Evento anterior / próximo do mesmo tipo |
| . | Move o evento selecionado para o quadro atual |
| Delete · Esc · N · G | Apagar · desmarcar · próximo alerta · grade da piscina |
| V | Liga/desliga a sobreposição |
| 1–8 · 0 | Raia dos próximos eventos (vários atletas no vídeo) · volta ao atleta da prova |

As métricas são recalculadas a cada mudança. “—” significa não medido (o motivo aparece ao
passar o mouse). Os tempos vêm sempre do relógio real de cada quadro (vídeos de celular têm
taxa variável).

## Desenvolvimento

Tudo também roda fora do Docker para desenvolver (Linux/WSL):

```bash
uv sync                                  # Python 3.12+, dependências travadas no uv.lock
uv run pytest                            # unidade (+ integração com TEST_DATABASE_URL)
uv run ruff check . && uv run ruff format --check .
cd frontend && npm ci && npm run dev     # front-end com recarga, API em :8000
```

Teste de navegador de ponta a ponta (com o sistema rodando):

```bash
sh tools/make_test_video.sh /tmp/teste.mp4 12
BASE_URL=http://localhost:8080 uv run --no-project --with playwright==1.56.0 \
  python tests/e2e/ui_smoke.py /tmp/teste.mp4
```

O vídeo de referência usado nos testes (`tests/golden/reference_race.mp4`) não vai para o
git; coloque-o nessa pasta para rodar o teste correspondente.

Regras para quem programa (inclusive agentes de IA): [`AGENTS.md`](AGENTS.md).
