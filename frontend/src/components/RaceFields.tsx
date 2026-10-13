import type { RaceInfo } from "../types";
import { unitLabel } from "../labels";

const POOLS: { label: string; length: number; unit: "m" | "yd" }[] = [
  { label: "25 m", length: 25, unit: "m" },
  { label: "50 m", length: 50, unit: "m" },
  { label: "25 jardas", length: 25, unit: "yd" },
];

function parseTime(s: string): number | null {
  const t = s.trim().replace(",", ".");
  if (!t) return null;
  // aceita "21.80" ou "1:02.35"
  const m = t.match(/^(?:(\d+):)?(\d+(?:\.\d+)?)$/);
  if (!m) return NaN;
  return (m[1] ? Number(m[1]) * 60 : 0) + Number(m[2]);
}

export function fmtInput(v: number | null | undefined) {
  return v == null ? "" : v.toFixed(2).replace(".", ",");
}

export default function RaceFields(props: {
  race: RaceInfo;
  onChange: (r: RaceInfo) => void;
}) {
  const { race, onChange } = props;
  const nLengths = race.distance / race.pool_length;
  const set = (patch: Partial<RaceInfo>) => onChange({ ...race, ...patch });
  const poolKey = `${race.pool_length}${race.pool_unit}`;
  const splits = race.official_splits_s ?? [];

  return (
    <div className="fields">
      <label>
        Estilo
        <select
          value={race.stroke}
          onChange={(e) => set({ stroke: e.target.value as RaceInfo["stroke"] })}
        >
          <option value="freestyle">Livre (crawl)</option>
          <option value="breaststroke">Peito</option>
        </select>
      </label>
      <label>
        Piscina
        <select
          value={poolKey}
          onChange={(e) => {
            const p = POOLS.find((x) => `${x.length}${x.unit}` === e.target.value)!;
            const distance = Math.max(p.length, Math.round(race.distance / p.length) * p.length);
            set({ pool_length: p.length, pool_unit: p.unit, distance, official_splits_s: [] });
          }}
        >
          {POOLS.map((p) => (
            <option key={p.label} value={`${p.length}${p.unit}`}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Distância
        <select
          value={race.distance}
          onChange={(e) => set({ distance: Number(e.target.value), official_splits_s: [] })}
        >
          {[50, 100].filter((d) => d % race.pool_length === 0).map((d) => (
            <option key={d} value={d}>
              {d} {unitLabel(race.pool_unit)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Raia
        <input
          type="number"
          min={1}
          max={10}
          value={race.lane ?? ""}
          onChange={(e) => set({ lane: e.target.value ? Number(e.target.value) : null })}
        />
      </label>
      <label>
        Tempo final oficial
        <input
          placeholder="ex.: 31,45"
          defaultValue={fmtInput(race.official_final_s)}
          onBlur={(e) => {
            const v = parseTime(e.target.value);
            set({ official_final_s: v == null || Number.isNaN(v) ? null : v });
          }}
        />
      </label>
      {Array.from({ length: nLengths - 1 }, (_, i) => (
        <label key={`${race.distance}-${race.pool_length}-${i}`}>
          Parcial oficial {(i + 1) * race.pool_length} {unitLabel(race.pool_unit)}
          <input
            placeholder="opcional"
            defaultValue={fmtInput(splits[i])}
            onBlur={(e) => {
              const v = parseTime(e.target.value);
              const next = [...splits];
              next[i] = v == null || Number.isNaN(v) ? NaN : v;
              // só parciais consecutivas a partir da primeira
              const clean: number[] = [];
              for (const s of next) {
                if (s == null || Number.isNaN(s)) break;
                clean.push(s);
              }
              set({ official_splits_s: clean });
            }}
          />
        </label>
      ))}
    </div>
  );
}
