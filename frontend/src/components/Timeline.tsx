import { useEffect, useRef, useState } from "react";
import { EVENT_COLOR, EVENT_LABEL } from "../labels";
import type { Alert, EventType, SwimEvent } from "../types";

const LABEL_W = 112;
const ROW_H = 26;
const ROWS: { label: string; types: EventType[] | "audio" | "alerts" }[] = [
  { label: "Áudio", types: "audio" },
  { label: "Largada", types: ["start_signal", "feet_off", "entry"] },
  { label: "Breakout", types: ["breakout"] },
  { label: "Braçadas", types: ["stroke"] },
  { label: "Parede", types: ["wall_hands", "wall_feet", "finish_touch"] },
  { label: "Marcas", types: ["mark_pass"] },
  { label: "Alertas", types: "alerts" },
];

export function nearestFrame(pts: number[], t: number): number {
  let lo = 0;
  let hi = pts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (pts[mid] < t) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && Math.abs(pts[lo - 1] - t) <= Math.abs(pts[lo] - t)) return lo - 1;
  return lo;
}

export default function Timeline(props: {
  pts: number[];
  frame: number;
  events: SwimEvent[];
  alerts: Alert[];
  waveform: { bins_per_s: number; peaks: number[] } | null;
  selectedId: string | null;
  zoom: number;
  onSeek: (frame: number) => void;
  onSelect: (id: string) => void;
}) {
  const { pts, frame, events, alerts, waveform, zoom } = props;
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const duration = pts.length ? pts[pts.length - 1] : 1;
  const t = pts[frame] ?? 0;
  const span = duration / zoom;
  const t0 = Math.min(Math.max(0, t - span / 2), Math.max(0, duration - span));
  const t1 = t0 + span;
  const plotW = Math.max(50, w - LABEL_W - 8);
  const X = (tt: number) => LABEL_W + ((tt - t0) / (t1 - t0)) * plotW;
  const H = ROWS.length * ROW_H + 18;

  function seekAt(clientX: number) {
    const r = box.current!.getBoundingClientRect();
    const x = clientX - r.left - LABEL_W;
    if (x < 0) return;
    props.onSeek(nearestFrame(pts, t0 + (x / plotW) * (t1 - t0)));
  }

  // ticks a cada 1, 2, 5 ou 10 s, conforme o zoom
  const step = [0.5, 1, 2, 5, 10].find((s) => span / s <= 14) ?? 10;
  const ticks: number[] = [];
  for (let k = Math.ceil(t0 / step) * step; k <= t1; k += step) ticks.push(k);

  let wave = "";
  if (waveform && waveform.peaks.length) {
    const y0 = ROW_H * 0 + ROW_H - 3;
    const pxPerBin = plotW / ((t1 - t0) * waveform.bins_per_s);
    const stride = Math.max(1, Math.floor(1 / Math.max(pxPerBin, 1e-6)));
    const parts: string[] = [];
    const a = Math.max(0, Math.floor(t0 * waveform.bins_per_s));
    const b = Math.min(waveform.peaks.length, Math.ceil(t1 * waveform.bins_per_s));
    for (let i = a; i < b; i += stride) {
      let p = 0;
      for (let j = i; j < Math.min(b, i + stride); j++) p = Math.max(p, waveform.peaks[j]);
      const x = X(i / waveform.bins_per_s).toFixed(1);
      parts.push(`M${x} ${y0}V${(y0 - p * (ROW_H - 6)).toFixed(1)}`);
    }
    wave = parts.join("");
  }

  return (
    <div className="timeline" ref={box}>
      <svg
        width={w}
        height={H}
        onMouseDown={(e) => {
          if ((e.target as Element).getAttribute("data-ev")) return;
          seekAt(e.clientX);
        }}
      >
        {ROWS.map((row, i) => (
          <g key={row.label}>
            <rect x={0} y={i * ROW_H} width={w} height={ROW_H} className={i % 2 ? "row odd" : "row"} />
            <text x={8} y={i * ROW_H + 17} className="row-label">
              {row.label}
            </text>
          </g>
        ))}
        {ticks.map((k) => (
          <g key={k}>
            <line x1={X(k)} x2={X(k)} y1={0} y2={ROWS.length * ROW_H} className="tick" />
            <text x={X(k) + 3} y={H - 4} className="tick-label">
              {k.toFixed(step < 1 ? 1 : 0)} s
            </text>
          </g>
        ))}
        {wave && <path d={wave} className="wave" />}
        {ROWS.map((row, i) => {
          if (row.types === "audio") return null;
          if (row.types === "alerts") {
            return alerts
              .filter((a) => a.t_from != null)
              .map((a, j) => (
                <rect
                  key={`al${j}`}
                  x={X(a.t_from!)}
                  y={i * ROW_H + 6}
                  width={Math.max(4, X(a.t_to ?? a.t_from!) - X(a.t_from!))}
                  height={ROW_H - 12}
                  className="alert-span"
                >
                  <title>{a.message}</title>
                </rect>
              ));
          }
          const types = row.types;
          return events
            .filter((e) => types.includes(e.type) && e.t >= t0 - 1 && e.t <= t1 + 1)
            .map((e) => {
              const sel = e.id === props.selectedId;
              const cx = X(e.t);
              const cy = i * ROW_H + ROW_H / 2;
              return (
                <g key={e.id}>
                  <rect
                    data-ev="1"
                    x={cx - (sel ? 5 : 3.5)}
                    y={cy - (sel ? 9 : 7)}
                    width={sel ? 10 : 7}
                    height={sel ? 18 : 14}
                    rx={2}
                    fill={EVENT_COLOR[e.type]}
                    stroke={sel ? "#fff" : e.image_xy ? "none" : "#0b1220"}
                    strokeWidth={sel ? 2 : 1}
                    strokeDasharray={e.image_xy || sel ? undefined : "2 2"}
                    style={{ cursor: "pointer" }}
                    onMouseDown={(ev) => {
                      ev.stopPropagation();
                      props.onSelect(e.id);
                    }}
                  >
                    <title>
                      {EVENT_LABEL[e.type]} · quadro {e.frame} · {e.t.toFixed(3)} s
                      {e.image_xy ? "" : " · sem posição"}
                    </title>
                  </rect>
                </g>
              );
            });
        })}
        <line x1={X(t)} x2={X(t)} y1={0} y2={ROWS.length * ROW_H} className="cursor" />
      </svg>
    </div>
  );
}
