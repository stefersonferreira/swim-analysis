import type { EventType, Metric, PoolUnit, Stroke } from "./types";

export const EVENT_LABEL: Record<EventType, string> = {
  start_signal: "Sinal de largada",
  feet_off: "Pés fora do bloco",
  entry: "Entrada na água",
  breakout: "Breakout",
  stroke: "Braçada",
  wall_hands: "Toque das mãos",
  wall_feet: "Pés na parede",
  finish_touch: "Toque final",
  mark_pass: "Passagem por marca",
};

/** Tecla de atalho que cria cada tipo de evento. */
export const EVENT_KEY: Record<EventType, string> = {
  start_signal: "I",
  feet_off: "O",
  entry: "E",
  breakout: "B",
  stroke: "S",
  wall_hands: "H",
  wall_feet: "W",
  finish_touch: "F",
  mark_pass: "P",
};

export const EVENT_COLOR: Record<EventType, string> = {
  start_signal: "#f2c94c",
  feet_off: "#f2994a",
  entry: "#56ccf2",
  breakout: "#27ae60",
  stroke: "#9b8cff",
  wall_hands: "#eb5757",
  wall_feet: "#eb5757",
  finish_touch: "#ffffff",
  mark_pass: "#2dd4bf",
};

export const STROKE_LABEL: Record<Stroke, string> = {
  freestyle: "Livre (crawl)",
  breaststroke: "Peito",
};

export const METRIC_LABEL: Record<string, string> = {
  reaction_s: "Reação",
  start_15m_s: "15 m da largada",
  start_breakout_m: "Breakout da largada",
  start_underwater_s: "Submerso na largada",
  start_underwater_speed_mps: "Velocidade submersa",
  turn_15m_s: "15 m da parede",
  turn_breakout_m: "Breakout da virada",
  turn_underwater_s: "Submerso na virada",
  turn_5m_inout_s: "Virada 5 m in/out",
  wall_time_s: "Tempo na parede",
  strokes: "Braçadas",
  tempo_s_per_cycle: "Tempo de ciclo",
  stroke_rate_cpm: "Frequência",
  swim_speed_mps: "Velocidade de nado",
  dpc_m: "Distância por ciclo",
  split_s: "Parcial",
  final_time_s: "Tempo final",
};

const UNIT_LABEL: Record<string, string> = {
  s: "s",
  m: "m",
  yd: "jd",
  "m/s": "m/s",
  "yd/s": "jd/s",
  count: "",
  "s/cycle": "s/ciclo",
  "cycles/min": "ciclos/min",
};

export function fmtMetric(m: Metric | undefined): string {
  if (!m || m.status !== "ok" || m.display_value == null) return "—";
  const v = m.display_value;
  const digits = m.unit === "count" ? 0 : m.unit === "cycles/min" ? 1 : 2;
  const num = v.toFixed(digits).replace(".", ",");
  const unit = UNIT_LABEL[m.display_unit] ?? m.display_unit;
  return unit ? `${num} ${unit}` : num;
}

export function fmtTime(t: number): string {
  return t.toFixed(2).replace(".", ",") + " s";
}

export function unitLabel(u: PoolUnit) {
  return u === "yd" ? "jd" : "m";
}
