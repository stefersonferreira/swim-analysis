import type { RaceInfo } from "../types";

const POOLS = [25, 50];

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
          value={race.pool_length}
          onChange={(e) => {
            const length = Number(e.target.value);
            const distance = Math.max(length, Math.round(race.distance / length) * length);
            set({ pool_length: length, distance, official_splits_s: [] });
          }}
        >
          {POOLS.map((p) => (
            <option key={p} value={p}>
              {p} m
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
              {d} m
            </option>
          ))}
        </select>
      </label>
      <label>
        Raia (necessária para a análise automática)
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
          Parcial oficial {(i + 1) * race.pool_length} m
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
