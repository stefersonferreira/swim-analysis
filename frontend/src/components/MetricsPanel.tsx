import { METRIC_LABEL, fmtMetric } from "../labels";
import type { Metric, RaceInfo } from "../types";

function Cell({ m }: { m: Metric | undefined }) {
  const missing = !m || m.status !== "ok";
  return (
    <td className={missing ? "missing" : m.source === "official" ? "official" : undefined}
        title={missing ? m?.reason ?? "" : m.source === "official" ? "Tempo oficial" : ""}>
      {fmtMetric(m)}
    </td>
  );
}

export default function MetricsPanel({ metrics, race }: { metrics: Metric[]; race: RaceInfo }) {
  const find = (name: string, k?: { length?: number; turn?: number }) =>
    metrics.find(
      (m) =>
        m.name === name &&
        (k?.length === undefined || m.length_index === k.length) &&
        (k?.turn === undefined || m.turn_index === k.turn),
    );
  const n = race.distance / race.pool_length;
  const start = ["reaction_s", "start_15m_s", "start_breakout_m", "start_underwater_s",
    "start_underwater_speed_mps"];
  const perLength = ["strokes", "tempo_s_per_cycle", "stroke_rate_cpm", "swim_speed_mps", "dpc_m"];
  const turns = ["turn_15m_s", "turn_breakout_m", "turn_underwater_s", "turn_5m_inout_s"];
  if (race.stroke === "breaststroke") turns.push("wall_time_s");

  return (
    <div className="metrics">
      <h3>Largada</h3>
      <table>
        <tbody>
          {start.map((name) => (
            <tr key={name}>
              <th>{METRIC_LABEL[name]}</th>
              <Cell m={find(name)} />
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Por piscina</h3>
      <table>
        <thead>
          <tr>
            <th />
            {Array.from({ length: n }, (_, k) => (
              <th key={k}>{(k + 1) * race.pool_length} m</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {perLength.map((name) => (
            <tr key={name}>
              <th>{METRIC_LABEL[name]}</th>
              {Array.from({ length: n }, (_, k) => (
                <Cell key={k} m={find(name, { length: k })} />
              ))}
            </tr>
          ))}
          <tr>
            <th>Tempo acumulado</th>
            {Array.from({ length: n }, (_, k) => (
              <Cell key={k} m={find(k === n - 1 ? "final_time_s" : "split_s", { length: k })} />
            ))}
          </tr>
        </tbody>
      </table>

      {n > 1 && (
        <>
          <h3>Viradas</h3>
          <table>
            <thead>
              <tr>
                <th />
                {Array.from({ length: n - 1 }, (_, k) => (
                  <th key={k}>{(k + 1) * race.pool_length} m</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {turns.map((name) => (
                <tr key={name}>
                  <th>{METRIC_LABEL[name]}</th>
                  {Array.from({ length: n - 1 }, (_, k) => (
                    <Cell key={k} m={find(name, { turn: k })} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <p className="muted small">
        “—” = não medido (passe o mouse para ver o motivo). Em destaque: tempo oficial.
      </p>
    </div>
  );
}
