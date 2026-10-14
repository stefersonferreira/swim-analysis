import { useMemo } from "react";
import "./overlay.css";
import { type Callout, type OverlayTimeline, br, clockText, stateAt } from "./state";

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

      {/* números da piscina atual */}
      {s.phase !== "ready" && s.phase != null && tl.has_swim_data !== false && (
        <div className="fx-card fx-stats">
          <Stat label="Piscina" value={`${s.length + 1}`} unit={`/${tl.n_lengths}`} />
          <Stat label={tl.stroke_word} value={String(s.strokes)} testid="fx-strokes" />
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
      {tl.track.d.length > 0 && (
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

      {s.showSummary && <Summary tl={tl} />}
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
    </div>
  );
}
