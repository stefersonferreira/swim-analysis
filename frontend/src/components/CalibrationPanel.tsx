import { useEffect, useState } from "react";
import { api } from "../api";
import type { Anchor, AnchorResult, PoolProfile, Video } from "../types";

export interface Pick {
  rope: number;
  x: number;
}

export function xOptions(pool: PoolProfile): number[] {
  return Array.from(new Set([0, ...pool.marks_m, pool.length_m])).sort((a, b) => a - b);
}

/** Próximo ponto sugerido: percorre as marcas ao longo da corda e depois troca de corda. */
export function nextPick(pool: PoolProfile, p: Pick): Pick {
  const xs = xOptions(pool);
  const i = xs.indexOf(p.x);
  if (i >= 0 && i < xs.length - 1) return { rope: p.rope, x: xs[i + 1] };
  return { rope: Math.min(pool.lanes, p.rope + 1), x: xs[0] };
}

export default function CalibrationPanel(props: {
  videoId: string;
  frame: number;
  pool: PoolProfile;
  anchors: Anchor[];
  results: AnchorResult[];
  pick: Pick;
  dirty: boolean;
  busy: boolean;
  message: string | null;
  onPool: (p: PoolProfile) => void;
  onPick: (p: Pick) => void;
  onAnchors: (a: Anchor[]) => void;
  onSave: () => void;
  onSeek: (frame: number) => void;
  onCopyFrom: (videoId: string) => void;
}) {
  const { pool, anchors, results, frame, pick } = props;
  const current = anchors.find((a) => a.frame === frame);
  const result = results.find((r) => r.frame === frame);
  const [others, setOthers] = useState<Video[]>([]);

  useEffect(() => {
    api
      .listVideos()
      .then((vs) => setOthers(vs.filter((v) => v.id !== props.videoId && v.has_calibration)))
      .catch(() => undefined);
  }, [props.videoId]);

  const setPoolNum = (k: keyof PoolProfile, v: string) => {
    const n = Number(v.replace(",", "."));
    if (!Number.isNaN(n) && n > 0) props.onPool({ ...pool, [k]: n });
  };

  function removePoint(i: number) {
    props.onAnchors(
      anchors.map((a) => (a.frame === frame ? { ...a, points: a.points.filter((_, j) => j !== i) } : a)),
    );
  }

  return (
    <div className="calib">
      <h3>Piscina</h3>
      <div className="fields compact">
        <label>
          Comprimento (m)
          <input defaultValue={pool.length_m} onBlur={(e) => setPoolNum("length_m", e.target.value)} />
        </label>
        <label>
          Raias
          <input defaultValue={pool.lanes} onBlur={(e) => setPoolNum("lanes", e.target.value)} />
        </label>
        <label>
          Largura da raia (m)
          <input
            defaultValue={pool.lane_width_m}
            onBlur={(e) => setPoolNum("lane_width_m", e.target.value)}
          />
        </label>
        <label>
          Marcas (m, a partir da saída)
          <input
            defaultValue={pool.marks_m.join("; ")}
            onBlur={(e) => {
              const ms = e.target.value
                .split(/[;\s]+/)
                .map((s) => Number(s.replace(",", ".")))
                .filter((x) => !Number.isNaN(x) && x > 0 && x < pool.length_m);
              props.onPool({ ...pool, marks_m: ms });
            }}
          />
        </label>
      </div>

      <h3>Âncoras</h3>
      <p className="muted small">
        Câmera parada: uma âncora basta. Clique pontos de posição conhecida (cordas na parede,
        marcas de 5 m e 15 m). Corda 0 = borda do lado da raia 1.
      </p>
      <div className="chips">
        {anchors.map((a) => {
          const r = results.find((x) => x.frame === a.frame);
          return (
            <button
              key={a.frame}
              className={`chip ${a.frame === frame ? "active" : ""} ${r?.accepted ? "ok" : r ? "bad" : ""}`}
              onClick={() => props.onSeek(a.frame)}
            >
              Quadro {a.frame} · {a.points.length} pts
            </button>
          );
        })}
        {!current && (
          <button className="btn small" onClick={() => props.onAnchors([...anchors, { frame, points: [] }])}>
            + Âncora neste quadro ({frame})
          </button>
        )}
      </div>

      {current && (
        <>
          <h3>Próximo clique</h3>
          <div className="fields compact">
            <label>
              Corda
              <select value={pick.rope} onChange={(e) => props.onPick({ ...pick, rope: Number(e.target.value) })}>
                {Array.from({ length: pool.lanes + 1 }, (_, i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Posição ao longo (m)
              <select value={pick.x} onChange={(e) => props.onPick({ ...pick, x: Number(e.target.value) })}>
                {xOptions(pool).map((x) => (
                  <option key={x} value={x}>
                    {x === 0 ? "0 (parede de saída)" : x === pool.length_m ? `${x} (parede oposta)` : x}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="hint">Clique no quadro onde a corda {pick.rope} cruza {pick.x} m.</p>
          <table className="points">
            <thead>
              <tr>
                <th>#</th>
                <th>Corda</th>
                <th>x (m)</th>
                <th>Erro</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {current.points.map((p, i) => {
                const err = result?.point_errors_m[i];
                const out = result && result.inliers[i] === false;
                return (
                  <tr key={i} className={out ? "bad" : undefined}>
                    <td>{i + 1}</td>
                    <td>{(p.pool_xy[1] / pool.lane_width_m).toFixed(0)}</td>
                    <td>{p.pool_xy[0]}</td>
                    <td>{err != null && !props.dirty ? `${(err * 100).toFixed(0)} cm` : ""}</td>
                    <td>
                      <button className="link" onClick={() => removePoint(i)}>
                        remover
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="row-actions">
            <button className="btn primary" disabled={props.busy || !props.dirty} onClick={props.onSave}>
              {props.busy ? "Calculando…" : "Salvar e calcular"}
            </button>
            <button
              className="btn danger small"
              onClick={() => props.onAnchors(anchors.filter((a) => a.frame !== frame))}
            >
              Remover âncora
            </button>
          </div>
          {result && !props.dirty && (
            <p className={result.accepted ? "ok" : "error"}>
              {result.accepted
                ? `Aceita · erro médio ${((result.mean_error_m ?? 0) * 100).toFixed(0)} cm, máximo ${((result.max_error_m ?? 0) * 100).toFixed(0)} cm`
                : "Não aceita"}
              {result.message ? ` · ${result.message}` : ""}
            </p>
          )}
        </>
      )}
      {props.message && <p className="error">{props.message}</p>}

      {others.length > 0 && (
        <>
          <h3>Mesma câmera de outro vídeo</h3>
          <select defaultValue="" onChange={(e) => e.target.value && props.onCopyFrom(e.target.value)}>
            <option value="">Copiar calibração de…</option>
            {others.map((v) => (
              <option key={v.id} value={v.id}>
                {v.title}
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}
