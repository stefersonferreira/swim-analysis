import { useMemo, useState } from "react";
import { EVENT_COLOR, fmtTime } from "../labels";
import type { EventType, RaceInfo, SwimEvent } from "../types";

/**
 * Marcação guiada, só com cliques: escolhe o atleta (raia), vê o passo a passo da prova e
 * marca cada momento no quadro em que o vídeo está. As teclas continuam valendo, mas
 * ninguém precisa delas.
 */

type Step = {
  key: string;
  type: EventType;
  label: string;
  tip: string;
  shared?: boolean; // vale para todas as raias (largada)
  many?: boolean; // vários por atleta (ciclos)
  nth?: number; // virada n (0 = primeira)
  optional?: boolean; // não entra no "próximo passo"
};

/** Marcas que costumam dar para ver: bandeiras de costas (5 m), meio da piscina, 15 m. */
export function markDistances(pool: number): number[] {
  const c = [5, 10, 15, pool / 2, pool - 15, pool - 10, pool - 5];
  return [...new Set(c.filter((m) => m > 0 && m < pool))].sort((a, b) => a - b);
}

const meters = (m: number) => String(m).replace(".", ",");

export function stepsFor(race: RaceInfo): Step[] {
  const breast = race.stroke === "breaststroke";
  const n = Math.max(1, Math.round(race.distance / race.pool_length));
  const steps: Step[] = [
    {
      key: "start",
      type: "start_signal",
      label: "Apito / largada",
      tip: "Vá até o quadro em que o apito (ou bipe) começa. Vale para todas as raias.",
      shared: true,
    },
    {
      key: "feet",
      type: "feet_off",
      label: "Saiu do bloco",
      tip: "Pare no último quadro em que o pé ainda toca o bloco.",
    },
    {
      key: "entry",
      type: "entry",
      label: "Entrou na água",
      tip: "Pare no primeiro quadro em que as mãos tocam a água.",
    },
    {
      key: "stroke",
      type: "stroke",
      label: breast ? "Ciclos" : "Braçadas",
      tip: breast
        ? "Marque cada ciclo quando a cabeça estiver no ponto mais alto. Pode marcar só o trecho em que o atleta aparece bem."
        : "Marque cada vez que uma mão entra na água. Pode marcar só o trecho em que o atleta aparece bem.",
      many: true,
    },
    {
      key: "marks",
      type: "mark_pass",
      label: "Marcas de distância",
      tip:
        "Opcional, mas é o que dá a velocidade: pare no quadro em que a cabeça passa por uma " +
        "marca conhecida (bandeira de costas a 5 m da parede, meio da piscina, troca de cor da " +
        "raia) e toque na distância. Conta a partir da parede de onde o atleta saiu nesta " +
        "piscina. Cada par de marcas vira a velocidade média daquele trecho.",
      many: true,
      optional: true,
    },
  ];
  for (let k = 0; k < n - 1; k++) {
    steps.push({
      key: `turn${k}`,
      type: breast ? "wall_hands" : "wall_feet",
      label: `Virada ${n > 2 ? k + 1 : ""}`.trim(),
      tip: breast
        ? "Pare no quadro em que as duas mãos tocam a parede da virada."
        : "Pare no quadro em que os pés tocam a parede da virada.",
      nth: k,
    });
  }
  steps.push({
    key: "finish",
    type: "finish_touch",
    label: "Toque final",
    tip: "Pare no quadro em que a mão toca a parede na chegada.",
  });
  return steps;
}

type Props = {
  race: RaceInfo;
  events: SwimEvent[];
  frame: number;
  t: number;
  lane: number | null;
  onLane: (lane: number | null) => void;
  onMark: (type: EventType, markM?: number) => void;
  onMove: (id: string) => void;
  onDelete: (id: string) => void;
  onGo: (e: SwimEvent) => void;
  selectedId: string | null;
};

export default function MarkingPanel(p: Props) {
  const { race, events } = p;
  const steps = useMemo(() => stepsFor(race), [race]);
  const [extraLanes, setExtraLanes] = useState<number[]>([]);
  const [adding, setAdding] = useState(false);

  // atletas: raias com marcações + as adicionadas agora; sem raias, o atleta da prova
  const lanes = useMemo(() => {
    const s = new Set<number>(extraLanes);
    for (const e of events) if (e.lane != null) s.add(e.lane);
    if (p.lane != null) s.add(p.lane);
    return [...s].sort((a, b) => a - b);
  }, [events, extraLanes, p.lane]);
  const mainHasEvents = events.some((e) => e.lane == null && e.type !== "start_signal");
  const showMain = lanes.length === 0 || mainHasEvents || p.lane == null;

  const mine = (e: SwimEvent) =>
    e.type === "start_signal" ? true : p.lane == null ? e.lane == null : e.lane === p.lane;
  const evs = events.filter(mine).sort((a, b) => a.t - b.t);
  const of = (s: Step) => {
    const list = evs.filter((e) => e.type === s.type);
    if (s.type === "start_signal") return list.filter((e) => e.lane == null);
    if (s.nth != null) return list.slice(s.nth, s.nth + 1);
    return list;
  };

  // próximo passo: o primeiro que falta (os ciclos só contam como faltando se não há nenhum)
  const next = steps.find((s) => !s.optional && of(s).length === 0) ?? null;

  const who = p.lane == null ? (race.lane ? `Raia ${race.lane}` : "Atleta") : `Raia ${p.lane}`;
  const cur = fmtTime(p.t);

  return (
    <section className="card marking" data-testid="marking">
      <h3>Marcação</h3>

      <div className="athletes" role="group" aria-label="Atleta">
        {showMain && (
          <button
            className={`chip ${p.lane == null ? "on" : ""}`}
            onClick={() => p.onLane(null)}
          >
            {race.lane ? `Raia ${race.lane}` : "Atleta da prova"}
          </button>
        )}
        {lanes.map((l) => (
          <button
            key={l}
            className={`chip ${p.lane === l ? "on" : ""}`}
            onClick={() => p.onLane(l)}
            data-testid={`lane-${l}`}
          >
            <span className="lane-dot">{l}</span> Raia {l}
          </button>
        ))}
        {adding ? (
          <span className="add-lane">
            {[1, 2, 3, 4, 5, 6, 7, 8]
              .filter((l) => !lanes.includes(l))
              .map((l) => (
                <button
                  key={l}
                  className="chip small"
                  onClick={() => {
                    setExtraLanes((x) => [...x, l]);
                    p.onLane(l);
                    setAdding(false);
                  }}
                >
                  {l}
                </button>
              ))}
            <button className="link small" onClick={() => setAdding(false)}>
              cancelar
            </button>
          </span>
        ) : (
          <button className="chip ghost" onClick={() => setAdding(true)} data-testid="add-lane">
            + Raia
          </button>
        )}
      </div>
      <p className="muted small">
        Vários atletas no vídeo? Adicione uma raia para cada um e marque um de cada vez.
      </p>

      {next && (
        <div className="next-step">
          <div className="small muted">
            Próximo · {who}
          </div>
          <b>{next.label}</b>
          <p className="small">{next.tip}</p>
          <button className="btn primary big" onClick={() => p.onMark(next.type)} data-testid="mark-next">
            Marcar “{next.many ? (race.stroke === "breaststroke" ? "Ciclo" : "Braçada") : next.label}” em {cur}
          </button>
        </div>
      )}

      {!next && (
        <div className="next-step done-box">
          <b>{who}: tudo marcado ✓</b>
          <p className="small">
            Marque outra raia, se houver, ou gere o vídeo em “Vídeo e relatório”. Para corrigir um
            momento, toque no horário dele, ajuste o quadro e use “Mudar p/ cá”.
          </p>
        </div>
      )}

      <ol className="steps">
        {steps.map((s) => {
          const list = of(s);
          const done = list.length > 0;
          const isNext = next?.key === s.key;
          return (
            <li key={s.key} className={`${done ? "done" : ""} ${isNext ? "next" : ""}`}>
              <span className="mark" style={{ borderColor: EVENT_COLOR[s.type] }}>
                {done ? "✓" : ""}
              </span>
              <div className="what">
                <div>
                  {s.label}
                  {s.many && done ? ` · ${list.length}` : ""}
                  {s.shared && <span className="muted small"> · todas as raias</span>}
                </div>
                {s.type === "mark_pass" && (
                  <>
                    <div className="muted small" title={s.tip}>
                      Opcional, mas é o que dá a velocidade. Pare quando a cabeça passa por uma
                      marca conhecida (bandeira a 5 m, meio da piscina) e toque na distância:
                    </div>
                    <div className="mark-btns">
                      {markDistances(race.pool_length).map((m) => (
                        <button
                          key={m}
                          className="btn small"
                          onClick={() => p.onMark("mark_pass", m)}
                          title={`A cabeça passa a ${meters(m)} m da parede de onde saiu, neste quadro`}
                          data-testid={`mark-${m}`}
                        >
                          {meters(m)} m
                        </button>
                      ))}
                    </div>
                  </>
                )}
                {done && !s.many && (
                  <button
                    className={`link small ${list[0].id === p.selectedId ? "sel" : ""}`}
                    onClick={() => p.onGo(list[0])}
                    title="Ir para este momento"
                  >
                    {fmtTime(list[0].t)}
                  </button>
                )}
                {done && !s.many && list[0].source === "auto" && (
                  <span className="muted small"> · automático</span>
                )}
                {done && s.many && (
                  <div className="cycle-chips">
                    {list.map((e) => (
                      <button
                        key={e.id}
                        className={`tchip ${e.id === p.selectedId ? "sel" : ""}`}
                        onClick={() => p.onGo(e)}
                        title={s.type === "mark_pass" ? "Ir para esta marca" : "Ir para este ciclo"}
                      >
                        {s.type === "mark_pass" && e.mark_m != null ? `${meters(e.mark_m)} m · ` : ""}
                        {e.t.toFixed(2).replace(".", ",")}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="acts">
                {s.many ? (
                  <>
                    {s.type !== "mark_pass" && (
                      <button className="btn small" onClick={() => p.onMark(s.type)}>
                        + aqui
                      </button>
                    )}
                    {done && (
                      <button
                        className="btn small ghost"
                        onClick={() => p.onDelete(list[list.length - 1].id)}
                        title="Apagar o último marcado"
                      >
                        Desfazer
                      </button>
                    )}
                  </>
                ) : done ? (
                  <>
                    <button
                      className="btn small ghost"
                      onClick={() => p.onMove(list[0].id)}
                      disabled={list[0].frame === p.frame}
                      title="Mudar este momento para o quadro atual"
                    >
                      Mudar p/ cá
                    </button>
                    <button
                      className="btn small ghost danger"
                      onClick={() => p.onDelete(list[0].id)}
                      title="Apagar"
                      aria-label={`Apagar ${s.label}`}
                    >
                      ✕
                    </button>
                  </>
                ) : (
                  <button className="btn small" onClick={() => p.onMark(s.type)}>
                    Marcar aqui
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
