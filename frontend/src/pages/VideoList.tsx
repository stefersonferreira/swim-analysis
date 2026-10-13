import { useEffect, useState } from "react";
import { api } from "../api";
import { Link } from "../App";
import { STROKE_LABEL, unitLabel } from "../labels";
import type { Video } from "../types";

const STATUS: Record<Video["status"], string> = {
  uploaded: "Na fila",
  processing: "Processando",
  ready: "Pronto",
  rejected: "Recusado",
  failed: "Falhou",
};

export default function VideoList() {
  const [videos, setVideos] = useState<Video[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [worker, setWorker] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .listVideos()
        .then((v) => alive && setVideos(v))
        .catch((e) => alive && setError(String(e.message || e)));
    load();
    const busy = setInterval(load, 3000);
    api.worker().then((w) => alive && setWorker(w)).catch(() => undefined);
    return () => {
      alive = false;
      clearInterval(busy);
    };
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Provas</h1>
        <Link to="/upload" className="btn primary">
          Enviar vídeo
        </Link>
      </div>
      {worker && (
        <p className="muted small">
          Processamento: {worker.worker === "offline" ? "worker fora do ar" : "worker ativo"}
          {" · "}
          {worker.gpu ? `GPU ${String(worker.nvidia_smi ?? "")}` : "sem GPU (CPU)"}
        </p>
      )}
      {error && <p className="error">{error}</p>}
      {videos && videos.length === 0 && (
        <div className="empty">
          <p>Nenhuma prova ainda.</p>
          <Link to="/upload" className="btn">
            Enviar o primeiro vídeo
          </Link>
        </div>
      )}
      {videos && videos.length > 0 && (
        <table className="list">
          <thead>
            <tr>
              <th>Prova</th>
              <th>Atleta</th>
              <th>Estilo</th>
              <th>Distância</th>
              <th>Status</th>
              <th>Enviado</th>
            </tr>
          </thead>
          <tbody>
            {videos.map((v) => (
              <tr key={v.id}>
                <td>
                  {v.status === "ready" ? <Link to={`/videos/${v.id}`}>{v.title}</Link> : v.title}
                  {v.error && <div className="error small">{v.error}</div>}
                </td>
                <td>{v.athlete ?? "—"}</td>
                <td>{STROKE_LABEL[v.race.stroke]}</td>
                <td>
                  {v.race.distance} {unitLabel(v.race.pool_unit)} (piscina {v.race.pool_length}{" "}
                  {unitLabel(v.race.pool_unit)})
                </td>
                <td>
                  <span className={`status ${v.status}`}>{STATUS[v.status]}</span>
                </td>
                <td className="muted">
                  {v.created_at ? new Date(v.created_at).toLocaleString("pt-BR") : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
