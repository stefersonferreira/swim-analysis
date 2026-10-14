import { useMemo } from "react";
import "./overlay.css";
import { type Callout, type OverlayLane, type OverlayState, type OverlayTimeline, br, clockText, stateAt } from "./state";

/**
 * Sobreposição ao vivo com a identidade Fluxi Swim. Fica por cima do quadro (pointer-events
 * desligado: cliques continuam indo para a marcação). Todas as medidas usam cqw/cqh do
 * quadro, então o desenho escala junto com o vídeo, em tela cheia ou não. O MP4 exportado
 * segue o mesmo desenho (pipeline/swimcv/overlay/render.py).
 */
export default function LiveOverlay({ tl, t }: { tl: OverlayTimeline; t: number }) {
  const s = useMemo(() => stateAt(tl, t), [tl, t]);
  const progress = s.raceD != null ? Math.min(1, Math.max(0, s.raceD / tl.distance)) : 0;
  const walls = Array.from({ length: tl.n_lengths - 1 }, (_, i) => (i + 1) * tl.pool_length);
  const swimming = s.phase === "swim" || s.phase === "underwater" || s.phase === "turn";
  const lanes = tl.lanes ?? [];

  return (
    <div className="fx-overlay" aria-label="Sobreposição da prova">
      {/* relógio e prova */}
      <div className="fx-card fx-clock">
        <div className="fx-wordmark">Fluxi Swim</div>
        <div className="fx-time" data-testid="fx-clock">
          {s.clock != null ? clockText(s.clock) : "–"}
        </div>
        <div className="fx-race">
          {tl.race_label}
          {tl.lane ? <span className="fx-chip">Raia {tl.lane}</span> : null}
        </div>
        {s.phaseLabel && s.phase !== "ready" && (
          <div className={`fx-phase fx-phase-${s.phase}`} data-testid="fx-phase">
            {s.phaseLabel}
          </div>
        )}
      </div>

      {/* várias raias: quadro comparativo ao vivo; um atleta: números da piscina atual */}
      {lanes.length > 0 && tl.t0 != null && t >= tl.t0 && !s.showSummary && <LanesBoard tl={tl} s={s} />}
      {lanes.length === 0 && s.phase !== "ready" && s.phase != null && tl.has_swim_data !== false && (
        <div className="fx-card fx-stats">
          <Stat label="Piscina" value={`${s.length + 1}`} unit={`/${tl.n_lengths}`} />
          <Stat
            label={tl.stroke_word}
            value={tl.strokes_partial ? "–" : String(s.strokes)}
            testid="fx-strokes"
          />
          <Stat label="Tempo de ciclo" value={s.tempo != null ? br(s.tempo) : "–"} unit="s" />
          <Stat label="Velocidade" value={swimming && s.speed != null ? br(s.speed) : "–"} unit="m/s" />
        </div>
      )}

      {/* nadador e balões */}
      {s.head && s.phase !== "ready" && (
        <div
          className="fx-ring"
          style={{ left: `${(100 * s.head[0]) / tl.width}%`, top: `${(100 * s.head[1]) / tl.height}%` }}
        />
      )}
      {s.callouts.map((c, i) => (
        <Balloon key={`${c.kind}-${c.t}`} c={c} tl={tl} head={s.head} stack={s.callouts.length - 1 - i} t={t} />
      ))}

      {/* barra de progresso (só com posições: parada em 0 só confundiria) */}
      {tl.track.d.length > 0 && lanes.length === 0 && (
      <div className="fx-progress">
        <div className="fx-track">
          <div className="fx-fill" style={{ width: `${100 * progress}%` }} />
          {walls.map((w, i) => {
            const split = tl.lengths[i]?.split;
            const passed = s.raceD != null && s.raceD >= w - 1e-6;
            return (
              <div key={w} className={`fx-tick ${passed ? "passed" : ""}`} style={{ left: `${(100 * w) / tl.distance}%` }}>
                <span className="fx-tick-label">
                  {w} m{passed && split != null ? <b> {clockText(split)}</b> : null}
                </span>
              </div>
            );
          })}
          <div className="fx-dot" style={{ left: `${100 * progress}%` }}>
            {s.raceD != null && s.phase !== "ready" && <span>{br(s.raceD, 1)} m</span>}
          </div>
        </div>
        <span className="fx-end">{tl.distance} m</span>
      </div>
      )}

      {s.showSummary && (lanes.length > 0 ? <LanesSummary tl={tl} lanes={lanes} /> : <Summary tl={tl} />)}
    </div>
  );
}

function Stat(props: { label: string; value: string; unit?: string; testid?: string }) {
  return (
    <div className="fx-stat">
      <div className="fx-stat-label">{props.label}</div>
      <div className="fx-stat-value" data-testid={props.testid}>
        {props.value}
        {props.unit && <small>{props.unit}</small>}
      </div>
    </div>
  );
}

function Balloon(props: {
  c: Callout;
  tl: OverlayTimeline;
  head: [number, number] | null;
  stack: number;
  t: number;
}) {
  const { c, tl, head, stack } = props;
  // entra com um pulo e sai esmaecendo
  const age = props.t - c.t;
  const left = c.until - props.t;
  const opacity = Math.min(1, age / 0.18, left / 0.35);
  const pop = age < 0.25 ? 0.85 + 0.15 * (age / 0.25) : 1;
  let style: React.CSSProperties;
  let below = false;
  if (head) {
    const x = Math.min(84, Math.max(16, (100 * head[0]) / tl.width));
    const yPct = (100 * head[1]) / tl.height;
    below = yPct < 38;
    style = below
      ? { left: `${x}%`, top: `calc(${yPct}% + var(--u) * ${3 + stack * 9})` }
      : { left: `${x}%`, bottom: `calc(${100 - yPct}% + var(--u) * ${3 + stack * 9})` };
  } else {
    style = { left: "50%", top: `calc(16cqh + var(--u) * ${stack * 9})` };
  }
  return (
    <div
      className={`fx-balloon fx-${c.kind} ${c.big ? "big" : ""} ${below ? "below" : ""} ${head ? "" : "free"}`}
      style={{ ...style, opacity, transform: `translateX(-50%) scale(${pop})` }}
      data-testid="fx-balloon"
    >
      <div className="fx-balloon-title">{c.title}</div>
      {c.value && <div className="fx-balloon-value">{c.value}</div>}
      {c.sub && <div className="fx-balloon-sub">{c.sub}</div>}
    </div>
  );
}

function Summary({ tl }: { tl: OverlayTimeline }) {
  return (
    <div className="fx-summary" data-testid="fx-summary">
      <div className="fx-wordmark">Fluxi Swim</div>
      <div className="fx-summary-title">{tl.title || tl.race_label}</div>
      <div className="fx-summary-sub">
        {[tl.athlete, tl.race_label, tl.pool_label].filter(Boolean).join(" · ")}
      </div>
      <div className="fx-summary-grid">
        {tl.summary.map(([k, v]) => (
          <div key={k} className="fx-summary-row">
            <span>{k}</span>
            <b>{v}</b>
          </div>
        ))}
      </div>
      {(tl.notes ?? []).map((n) => (
        <div key={n} className="fx-lanes-note">
          {n}
        </div>
      ))}
    </div>
  );
}

function LaneChip({ lane }: { lane: number }) {
  return <span className="fx-lane-chip">{lane}</span>;
}

/** Ao vivo: saída, ciclos e ritmo de cada raia; o tempo aparece quando ela chega. */
function LanesBoard({ tl, s }: { tl: OverlayTimeline; s: OverlayState }) {
  const info = new Map((tl.lanes ?? []).map((lr) => [lr.lane, lr]));
  const showCount = !tl.strokes_partial;
  return (
    <div
      className="fx-card fx-lanes"
      data-testid="fx-lanes"
      style={{ gridTemplateColumns: `repeat(${showCount ? 5 : 4}, auto)` }}
    >
      <span className="fx-lanes-head">Raia</span>
      <span className="fx-lanes-head">Saída</span>
      {showCount && <span className="fx-lanes-head">{tl.stroke_word}</span>}
      <span className="fx-lanes-head">Ritmo</span>
      <span className="fx-lanes-head">Tempo</span>
      {s.lanes.map((r) => {
        const lr = info.get(r.lane);
        const ft = lr?.final_time ?? null;
        const sd = r.started ? (lr?.start_delay ?? null) : null;
        return [
          <LaneChip key={`c${r.lane}`} lane={r.lane} />,
          <b key={`d${r.lane}`} className={sd != null ? "" : "muted"}>
            {sd != null ? (
              <>
                {br(sd)}
                <small>s</small>
              </>
            ) : (
              "–"
            )}
          </b>,
          showCount ? (
            <b key={`s${r.lane}`} data-testid="fx-lane-strokes">
              {r.strokes}
            </b>
          ) : null,
          <b key={`r${r.lane}`} className={r.tempo ? "" : "muted"}>
            {r.tempo ? (
              <>
                {(60 / r.tempo).toFixed(0)}
                <small>/min</small>
              </>
            ) : (
              "–"
            )}
          </b>,
          <b key={`t${r.lane}`} className={r.finished && ft != null ? "mint" : "muted"}>
            {r.finished && ft != null ? clockText(ft) : "–"}
          </b>,
        ];
      })}
    </div>
  );
}

/** Fim: uma linha por raia, lado a lado. "–" = não visto no vídeo. */
function LanesSummary({ tl, lanes }: { tl: OverlayTimeline; lanes: OverlayLane[] }) {
  const kinds = new Set(lanes.map((l) => l.start_delay_kind).filter(Boolean));
  const notes: string[] = [];
  if (kinds.has("entry")) notes.push("Saída: do apito até entrar na água");
  else if (kinds.has("feet_off")) notes.push("Saída: do apito até sair do bloco");
  if (lanes.some((l) => l.final_time == null)) notes.push("– : chegada fora do vídeo");
  notes.push("Ritmo: ciclos de braço por minuto", ...(tl.notes ?? []));
  const cols: [string, (l: OverlayLane) => string][] = [
    ["Saída", (l) => (l.start_delay != null ? `${br(l.start_delay)} s` : "–")],
    [tl.stroke_word, (l) => (l.n_strokes ? String(l.n_strokes) : "–")],
    ["Ritmo", (l) => (l.rate ? `${l.rate.toFixed(0)}/min` : "–")],
    ["Tempo", (l) => (l.final_time ? clockText(l.final_time) : "–")],
    ["Dif.", (l) => (l.behind == null ? "–" : l.behind === 0 ? "1º" : `+${br(l.behind)} s`)],
    ["Velocidade", (l) => (l.speed ? `${br(l.speed)} m/s` : "–")],
  ];
  if (tl.strokes_partial) cols.splice(1, 1);
  return (
    <div className="fx-summary" data-testid="fx-summary">
      <div className="fx-wordmark">Fluxi Swim</div>
      <div className="fx-summary-title">{tl.title || tl.race_label}</div>
      <div className="fx-summary-sub">{[tl.race_label, tl.pool_label].filter(Boolean).join(" · ")}</div>
      <div className="fx-lanes-table" style={{ gridTemplateColumns: `auto repeat(${cols.length}, auto)` }}>
        <span className="fx-lanes-head">Raia</span>
        {cols.map(([name]) => (
          <span key={name} className="fx-lanes-head">
            {name}
          </span>
        ))}
        {lanes.map((l) => [
          <LaneChip key={`c${l.lane}`} lane={l.lane} />,
          ...cols.map(([name, f]) => {
            const v = f(l);
            return (
              <b key={`${name}${l.lane}`} className={v === "–" ? "muted" : ""}>
                {v}
              </b>
            );
          }),
        ])}
      </div>
      {notes.map((n) => (
        <div key={n} className="fx-lanes-note">
          {n}
        </div>
      ))}
    </div>
  );
}
