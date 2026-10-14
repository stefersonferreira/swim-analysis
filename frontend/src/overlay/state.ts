/**
 * Estado da sobreposição num instante. Mesmas regras de state_at em
 * pipeline/swimcv/overlay/timeline.py (o MP4 exportado usa a versão Python).
 */

export interface Callout {
  t: number;
  until: number;
  kind: "reaction" | "breakout" | "15m" | "split" | "finish";
  title: string;
  value: string;
  sub: string;
  big: boolean;
}

export interface Phase {
  kind: "ready" | "start" | "underwater" | "swim" | "turn" | "finish";
  label: string;
  t0: number;
  t1: number | null;
  length: number;
}

export interface OverlayLength {
  index: number;
  t_start: number | null;
  t_end: number | null;
  strokes: [number, number | null][];
  tempo: number | null;
  speed: number | null;
  dpc: number | null;
  split: number | null;
}

/** Uma raia no quadro comparativo (vários atletas no mesmo vídeo). */
export interface OverlayLane {
  lane: number;
  strokes: [number, number | null][];
  n_strokes: number;
  start_delay: number | null;
  start_delay_kind: "feet_off" | "entry" | null;
  tempo: number | null;
  rate: number | null;
  finish_t: number | null;
  final_time: number | null;
  speed: number | null;
  dpc: number | null;
  start_t?: number | null;
  behind?: number | null;
}

export interface LaneState {
  lane: number;
  strokes: number;
  tempo: number | null;
  finished: boolean;
  started: boolean;
  pulse: boolean;
}

export interface OverlayTimeline {
  schema_version: number;
  width: number;
  height: number;
  duration_s: number;
  title: string;
  athlete: string | null;
  race_label: string;
  pool_label: string;
  lane: number | null;
  distance: number;
  pool_length: number;
  n_lengths: number;
  has_swim_data?: boolean;
  stroke_word: string;
  t0: number | null;
  t_finish: number | null;
  clock_end: number | null;
  phases: Phase[];
  lengths: OverlayLength[];
  callouts: Callout[];
  track: { t: number[]; d: number[]; x: (number | null)[]; y: (number | null)[]; v: (number | null)[] };
  summary: [string, string][];
  lanes?: OverlayLane[];
  notes?: string[];
  /** braçadas marcadas só num trecho: a contagem aparece como "–" */
  strokes_partial?: boolean;
}

export interface OverlayState {
  clock: number | null;
  phase: Phase["kind"] | null;
  phaseLabel: string | null;
  length: number;
  strokes: number;
  tempo: number | null;
  speed: number | null;
  raceD: number | null;
  head: [number, number] | null;
  callouts: Callout[];
  showSummary: boolean;
  lanes: LaneState[];
  /** acabou de acontecer uma braçada/ciclo: o número pisca */
  pulse: boolean;
}

const CALLOUT_S = 2.6;
const PULSE_S = 0.35;
const SUMMARY_TAIL_S = 0.3;

function interp(ts: number[], vs: (number | null)[], t: number): number | null {
  if (!ts.length) return null;
  // primeiro índice com ts[i] >= t (como numpy.searchsorted)
  let lo = 0;
  let hi = ts.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (ts[mid] < t) lo = mid + 1;
    else hi = mid;
  }
  const i = lo;
  if (i <= 0) return vs[0];
  if (i >= ts.length) return vs[vs.length - 1];
  const a = vs[i - 1];
  const b = vs[i];
  if (a == null || b == null) return t - ts[i - 1] < ts[i] - t ? a : b;
  const f = (t - ts[i - 1]) / (ts[i] - ts[i - 1]);
  return a + f * (b - a);
}

export function stateAt(tl: OverlayTimeline, t: number): OverlayState {
  const { t0, t_finish: tf } = tl;
  const clock = t0 == null ? null : tf != null && t >= tf ? tl.clock_end : Math.max(0, t - t0);
  const ph = tl.phases.find((p) => p.t0 <= t && (p.t1 == null || t < p.t1)) ?? null;
  let k = ph ? ph.length : 0;
  for (const ln of tl.lengths) {
    if (ln.t_end != null && t >= ln.t_end && ln.index < tl.n_lengths - 1) k = Math.max(k, ln.index + 1);
  }
  const ln = tl.lengths[Math.min(k, tl.lengths.length - 1)];
  const done = ln.strokes.filter((s) => s[0] <= t);
  const tempo = [...done].reverse().find((s) => s[1] != null)?.[1] ?? null;
  const tr = tl.track;
  const x = interp(tr.t, tr.x, t);
  const y = interp(tr.t, tr.y, t);
  const kind = ph?.kind ?? null;
  const v = kind === "swim" || kind === "underwater" || kind === "turn" ? interp(tr.t, tr.v, t) : null;
  const lanes: LaneState[] = (tl.lanes ?? []).map((lr) => {
    const ld = lr.strokes.filter((s) => s[0] <= t);
    return {
      lane: lr.lane,
      strokes: ld.length,
      tempo: [...ld].reverse().find((s) => s[1] != null)?.[1] ?? null,
      finished: lr.finish_t != null && t >= lr.finish_t,
      started: lr.start_t != null && t >= lr.start_t,
      pulse: ld.length > 0 && t - ld[ld.length - 1][0] < PULSE_S,
    };
  });
  let clockNow = clock;
  let summary =
    tf != null && t >= tf && t >= Math.min(tf + CALLOUT_S * 1.6, (tl.duration_s || 1e9) - SUMMARY_TAIL_S);
  if (lanes.length) {
    const fins = (tl.lanes ?? []).map((lr) => lr.finish_t);
    const allIn = fins.every((f) => f != null);
    summary =
      (allIn && t >= Math.max(...(fins as number[])) + CALLOUT_S * 1.6) ||
      (!!tl.duration_s && t >= tl.duration_s - SUMMARY_TAIL_S);
    // relógio para na chegada da última raia
    const last = Math.max(...(fins as number[]));
    if (allIn && t0 != null && tf == null && t >= last) clockNow = last - t0;
  }
  return {
    clock: clockNow,
    pulse: done.length > 0 && t - done[done.length - 1][0] < PULSE_S,
    phase: kind,
    phaseLabel: ph?.label ?? null,
    length: ln.index,
    strokes: done.length,
    tempo,
    speed: v,
    raceD: interp(tr.t, tr.d, t),
    head: x != null && y != null ? [x, y] : null,
    callouts: tl.callouts.filter((c) => c.t <= t && t < c.until).slice(-2),
    // resumo depois do balão de chegada, ou no fim do vídeo se ele acabar antes; com várias
    // raias, depois da última chegada ou no fim do vídeo
    showSummary: summary,
    lanes,
  };
}

export function br(v: number, digits = 2): string {
  return v.toFixed(digits).replace(".", ",");
}

export function clockText(s: number): string {
  s = Math.max(0, s);
  const m = Math.floor(s / 60);
  const r = s - 60 * m;
  return m >= 1 ? `${m}:${r.toFixed(2).padStart(5, "0").replace(".", ",")}` : br(r);
}
